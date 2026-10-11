"""persistence_sqlite - local SQLite storage for the appliance.

Tables: crm_interactions, client_consent_events (+ current-consent view in
code), financial_ledger, client_drawers (+ identity history),
client_drawer_files.

Wiring status (2026-10-11): no spoke writes to this store. Agents 14 and 15
keep their state in memory. The only runtime reader is tools/dashboard.py.
The store is ready for that wiring; it is not yet a system of record.

Guarantees (fixed 2026-10-11, audit S-2, S-3, RL-1):
  - Money is exact. amount / commission_rate / balance are stored as decimal
    TEXT and returned as decimal.Decimal. A Python float is refused, because
    the rounding error is already in the float (0.1 + 0.2 != 0.3). Before:
    REAL columns, 0.1 + 0.2 came back 0.30000000000000004.
  - Append-only ("the log is written in ink", Agent 14 tuple layer).
    crm_interactions, financial_ledger, client_drawer_files,
    client_consent_events and client_drawer_identity_history reject UPDATE
    and DELETE with a trigger. Corrections are new rows. Before: rows were
    editable in place.
  - Consent keeps its history. Each update_client_consent() call appends one
    event per channel; get_client_consent() returns the latest statement per
    channel and get_consent_history() returns every event. Before: one row
    per client, overwritten.
  - A drawer's identity is never silently replaced. Registering an existing
    client_id with a different name/address/role raises
    DrawerIdentityConflict unless update_identity=True, which records the
    previous identity in client_drawer_identity_history. Before: a second
    register overwrote Alice/1 Oak with Mallory/9 Elm.
  - File databases run in WAL journal mode.

Storage location: use a local disk. SQLite's locking is not reliable over
network file systems (SMB/NFS shares, including NAS shares), so do not
point db_path at a network share.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, InvalidOperation
from typing import Optional, Union

SCHEMA_VERSION = 2
Money = Union[Decimal, int, str]

_APPEND_ONLY_TABLES = ("crm_interactions", "financial_ledger", "client_drawer_files",
                       "client_consent_events", "client_drawer_identity_history")


class DrawerIdentityConflict(ValueError):
    """Registering an existing drawer with a different identity."""


class SchemaMismatch(RuntimeError):
    """The database file was created by an incompatible schema version."""


def _to_decimal_text(value: Optional[Money], field: str) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field}: pass Decimal, int or a decimal string, not {type(value).__name__} "
                        f"(a float already carries rounding error)")
    try:
        d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    except InvalidOperation:
        raise ValueError(f"{field}: {value!r} is not a decimal number") from None
    if not d.is_finite():
        raise ValueError(f"{field}: {value!r} is not finite")
    return str(d)


def _from_decimal_text(value: Optional[str]) -> Optional[Decimal]:
    return None if value is None else Decimal(value)


class ApplianceStorage:
    """SQLite storage for the appliance deployment (see module docstring)."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        if db_path != ":memory:":
            mode = self.conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            self.journal_mode = mode
        else:
            self.journal_mode = "memory"
        self._init_db()

    def close(self):
        """Closes the active database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _init_db(self):
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        row = c.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        has_tables = c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
                               "AND name IN ('financial_ledger','client_consent')").fetchone()[0]
        if row is None and has_tables:
            raise SchemaMismatch(
                f"{self.db_path}: created by the schema-1 store (REAL money columns, overwritable "
                f"consent). No spoke wrote to that store; move the file aside and reopen.")
        if row is not None and int(row["value"]) != SCHEMA_VERSION:
            raise SchemaMismatch(f"{self.db_path}: schema version {row['value']}, expected {SCHEMA_VERSION}")

        c.execute("""
            CREATE TABLE IF NOT EXISTS crm_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_context_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_crm_ctx ON crm_interactions(client_context_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS client_consent_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_context_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                value TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_consent_ctx ON client_consent_events(client_context_id)")

        # Money columns are TEXT on purpose: exact decimal strings.
        c.execute("""
            CREATE TABLE IF NOT EXISTS financial_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_context_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount TEXT,
                commission_rate TEXT,
                balance TEXT,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_finance_ctx ON financial_ledger(client_context_id)")

        c.execute("""
            CREATE TABLE IF NOT EXISTS client_drawers (
                client_id TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                property_address TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'seller',
                assigned_agent TEXT NOT NULL DEFAULT '00',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS client_drawer_identity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                client_name TEXT NOT NULL,
                property_address TEXT NOT NULL,
                role TEXT NOT NULL,
                assigned_agent TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                replaced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")

        c.execute("""
            CREATE TABLE IF NOT EXISTS client_drawer_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                category TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_drawer_files_client ON client_drawer_files(client_id)")

        for table in _APPEND_ONLY_TABLES:
            for op in ("UPDATE", "DELETE"):
                c.execute(f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_no_{op.lower()}
                    BEFORE {op} ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only: add a correcting row'); END""")

        c.execute("INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('version', ?)", (str(SCHEMA_VERSION),))
        self.conn.commit()

    # --- CRM ------------------------------------------------------------------

    def record_crm_interaction(self, client_context_id: str, agent_id: str, kind: str, payload: dict) -> int:
        """Appends a CRM interaction log entry."""
        cur = self.conn.execute(
            "INSERT INTO crm_interactions (client_context_id, agent_id, kind, payload_json) VALUES (?, ?, ?, ?)",
            (client_context_id, agent_id, kind, json.dumps(payload)))
        self.conn.commit()
        return cur.lastrowid

    def update_client_consent(self, client_context_id: str, consent_channels: dict, source: str = ""):
        """Appends one consent event per channel. Nothing is overwritten."""
        if not isinstance(consent_channels, dict) or not consent_channels:
            raise ValueError("consent_channels must be a non-empty {channel: value} dict")
        with self.conn:
            for channel, value in consent_channels.items():
                self.conn.execute(
                    "INSERT INTO client_consent_events (client_context_id, channel, value, source) "
                    "VALUES (?, ?, ?, ?)", (client_context_id, str(channel), str(value), source))

    def get_client_consent(self, client_context_id: str) -> dict:
        """Latest stated value per channel. Owner note: a later opt-in after an
        opt-out is returned as the current value; the opt-out stays in
        get_consent_history()."""
        rows = self.conn.execute(
            "SELECT channel, value FROM client_consent_events WHERE client_context_id = ? ORDER BY id ASC",
            (client_context_id,)).fetchall()
        current: dict = {}
        for r in rows:
            current[r["channel"]] = r["value"]
        return current

    def get_consent_history(self, client_context_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT channel, value, source, created_at FROM client_consent_events "
            "WHERE client_context_id = ? ORDER BY id ASC", (client_context_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_crm_interactions(self, client_context_id: str) -> list[dict]:
        """Fetches interaction history for a given client context."""
        rows = self.conn.execute(
            "SELECT agent_id, kind, payload_json, created_at FROM crm_interactions "
            "WHERE client_context_id = ? ORDER BY id ASC", (client_context_id,)).fetchall()
        return [{"agent_id": r["agent_id"], "kind": r["kind"],
                 "payload": json.loads(r["payload_json"]), "created_at": r["created_at"]} for r in rows]

    # --- Financial ledger -----------------------------------------------------

    def record_financial_entry(self, client_context_id: str, event_type: str,
                               amount: Optional[Money] = None, commission_rate: Optional[Money] = None,
                               balance: Optional[Money] = None, payload: Optional[dict] = None) -> int:
        """Appends a ledger entry. Money values: Decimal, int or decimal string."""
        vals = (_to_decimal_text(amount, "amount"), _to_decimal_text(commission_rate, "commission_rate"),
                _to_decimal_text(balance, "balance"))
        cur = self.conn.execute(
            "INSERT INTO financial_ledger (client_context_id, event_type, amount, commission_rate, balance, "
            "payload_json) VALUES (?, ?, ?, ?, ?, ?)",
            (client_context_id, event_type, *vals, json.dumps(payload or {})))
        self.conn.commit()
        return cur.lastrowid

    def get_financial_history(self, client_context_id: str) -> list[dict]:
        """Ledger entries for a client context; money fields are Decimal."""
        rows = self.conn.execute(
            "SELECT event_type, amount, commission_rate, balance, payload_json, created_at "
            "FROM financial_ledger WHERE client_context_id = ? ORDER BY id ASC", (client_context_id,)).fetchall()
        return [{"event_type": r["event_type"], "amount": _from_decimal_text(r["amount"]),
                 "commission_rate": _from_decimal_text(r["commission_rate"]),
                 "balance": _from_decimal_text(r["balance"]),
                 "payload": json.loads(r["payload_json"]), "created_at": r["created_at"]} for r in rows]

    # --- Client drawers -------------------------------------------------------

    def register_client_drawer(self, client_id: str, client_name: str, property_address: str,
                               role: str = "seller", assigned_agent: str = "00",
                               metadata: Optional[dict] = None, update_identity: bool = False):
        """Registers a client drawer. Re-registering the same identity is a
        no-op; a different identity raises DrawerIdentityConflict unless
        update_identity=True, which keeps the old identity in history."""
        meta = json.dumps(metadata or {})
        with self.conn:
            row = self.conn.execute("SELECT * FROM client_drawers WHERE client_id = ?", (client_id,)).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO client_drawers (client_id, client_name, property_address, role, assigned_agent, "
                    "metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (client_id, client_name, property_address, role, assigned_agent, meta))
                return
            new = (client_name, property_address, role, assigned_agent, meta)
            old = (row["client_name"], row["property_address"], row["role"], row["assigned_agent"],
                   row["metadata_json"])
            if new == old:
                return
            if not update_identity:
                raise DrawerIdentityConflict(
                    f"drawer {client_id!r} is registered to {row['client_name']!r} / {row['property_address']!r}; "
                    f"refusing to replace it with {client_name!r} / {property_address!r} "
                    f"(pass update_identity=True for a deliberate change)")
            self.conn.execute(
                "INSERT INTO client_drawer_identity_history (client_id, client_name, property_address, role, "
                "assigned_agent, metadata_json) VALUES (?, ?, ?, ?, ?, ?)", (client_id, *old))
            self.conn.execute(
                "UPDATE client_drawers SET client_name=?, property_address=?, role=?, assigned_agent=?, "
                "metadata_json=? WHERE client_id=?", (*new, client_id))

    def get_drawer_identity_history(self, client_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT client_name, property_address, role, assigned_agent, replaced_at "
            "FROM client_drawer_identity_history WHERE client_id = ? ORDER BY id ASC", (client_id,)).fetchall()
        return [dict(r) for r in rows]

    def record_drawer_file(self, client_id: str, agent_id: str, category: str, filename: str,
                           file_path: str, file_hash: str, size_bytes: int) -> int:
        """Indexes an artifact or document in the client's drawer."""
        cur = self.conn.execute(
            "INSERT INTO client_drawer_files (client_id, agent_id, category, filename, file_path, file_hash, "
            "size_bytes) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (client_id, agent_id, category, filename, file_path, file_hash, size_bytes))
        self.conn.commit()
        return cur.lastrowid

    def get_drawer_files(self, client_id: str, category: Optional[str] = None) -> list[dict]:
        """Retrieves all files indexed for a specific client drawer."""
        sql = ("SELECT id, agent_id, category, filename, file_path, file_hash, size_bytes, created_at "
               "FROM client_drawer_files WHERE client_id = ?")
        args: tuple = (client_id,)
        if category:
            sql += " AND category = ?"
            args += (category,)
        rows = self.conn.execute(sql + " ORDER BY id ASC", args).fetchall()
        return [dict(r) for r in rows]

    def list_client_drawers(self) -> list[dict]:
        """Lists all registered client drawers with file counts."""
        rows = self.conn.execute("""
            SELECT d.client_id, d.client_name, d.property_address, d.role, d.assigned_agent,
                   d.created_at, COUNT(f.id) as file_count
            FROM client_drawers d
            LEFT JOIN client_drawer_files f ON d.client_id = f.client_id
            GROUP BY d.client_id
            ORDER BY d.created_at DESC""").fetchall()
        return [dict(r) for r in rows]
