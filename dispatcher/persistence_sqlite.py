"""persistence_sqlite - Transactional Local Appliance SQLite Persistence Layer.

Provides zero-daemon ACID transactional persistence designed to reside on
local storage or the repurposed Drobo NAS RAID partition.

Survives VM reboots, container restarts, and physical power cycles without
external database infrastructure (Postgres/MySQL).

Persists:
  1. Agent 14 CRM interactions, client consent registries, and communication logs.
  2. Agent 15 Financial ledgers, commission calculations, invoices, and audit checkpoints.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


class ApplianceStorage:
    """ACID transactional storage for the appliance deployment."""

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
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
        cursor = self.conn.cursor()
        # 1. CRM Interactions table (Spoke 14)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crm_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_context_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_crm_ctx 
            ON crm_interactions(client_context_id)
        """)

        # 2. Client Consent table (Spoke 14)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_consent (
                client_context_id TEXT PRIMARY KEY,
                channels_json TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Financial Ledger table (Spoke 15)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS financial_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_context_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                amount REAL,
                commission_rate REAL,
                balance REAL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_finance_ctx 
            ON financial_ledger(client_context_id)
        """)

        # 4. Client Drawers registry (One Client, One Drawer)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_drawers (
                client_id TEXT PRIMARY KEY,
                client_name TEXT NOT NULL,
                property_address TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'seller',
                assigned_agent TEXT NOT NULL DEFAULT '00',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. Client Drawer Files index
        cursor.execute("""
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
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_drawer_files_client
            ON client_drawer_files(client_id)
        """)
        self.conn.commit()

    # --- Spoke 14 CRM Methods ----------------------------------------------

    def record_crm_interaction(
        self,
        client_context_id: str,
        agent_id: str,
        kind: str,
        payload: dict
    ) -> int:
        """Appends a CRM interaction log entry."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO crm_interactions (client_context_id, agent_id, kind, payload_json)
            VALUES (?, ?, ?, ?)
        """, (client_context_id, agent_id, kind, json.dumps(payload)))
        self.conn.commit()
        return cursor.lastrowid

    def update_client_consent(
        self,
        client_context_id: str,
        consent_channels: dict
    ):
        """Sets or merges channel consent for a client context."""
        existing = self.get_client_consent(client_context_id)
        merged = {**existing, **consent_channels}
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO client_consent (client_context_id, channels_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(client_context_id) DO UPDATE SET
                channels_json = excluded.channels_json,
                updated_at = CURRENT_TIMESTAMP
        """, (client_context_id, json.dumps(merged)))
        self.conn.commit()

    def get_client_consent(self, client_context_id: str) -> dict:
        """Retrieves consent dictionary for a client context."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT channels_json FROM client_consent WHERE client_context_id = ?
        """, (client_context_id,))
        row = cursor.fetchone()
        if row:
            return json.loads(row["channels_json"])
        return {}

    def get_crm_interactions(self, client_context_id: str) -> list[dict]:
        """Fetches interaction history for a given client context."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT agent_id, kind, payload_json, created_at 
            FROM crm_interactions 
            WHERE client_context_id = ? 
            ORDER BY id ASC
        """, (client_context_id,))
        rows = cursor.fetchall()
        return [
            {
                "agent_id": r["agent_id"],
                "kind": r["kind"],
                "payload": json.loads(r["payload_json"]),
                "created_at": r["created_at"]
            }
            for r in rows
        ]

    # --- Spoke 15 Financial Methods ----------------------------------------

    def record_financial_entry(
        self,
        client_context_id: str,
        event_type: str,
        amount: Optional[float] = None,
        commission_rate: Optional[float] = None,
        balance: Optional[float] = None,
        payload: Optional[dict] = None
    ) -> int:
        """Appends a financial transaction entry to the ledger."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO financial_ledger 
            (client_context_id, event_type, amount, commission_rate, balance, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            client_context_id,
            event_type,
            amount,
            commission_rate,
            balance,
            json.dumps(payload or {})
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_financial_history(self, client_context_id: str) -> list[dict]:
        """Fetches financial ledger entries for a client context."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT event_type, amount, commission_rate, balance, payload_json, created_at
            FROM financial_ledger
            WHERE client_context_id = ?
            ORDER BY id ASC
        """, (client_context_id,))
        rows = cursor.fetchall()
        return [
            {
                "event_type": r["event_type"],
                "amount": r["amount"],
                "commission_rate": r["commission_rate"],
                "balance": r["balance"],
                "payload": json.loads(r["payload_json"]),
                "created_at": r["created_at"]
            }
            for r in rows
        ]

    # --- Client Drawer Methods (One Client, One Drawer) ---------------------

    def register_client_drawer(
        self,
        client_id: str,
        client_name: str,
        property_address: str,
        role: str = "seller",
        assigned_agent: str = "00",
        metadata: Optional[dict] = None
    ):
        """Registers a new isolated client drawer."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO client_drawers 
            (client_id, client_name, property_address, role, assigned_agent, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(client_id) DO UPDATE SET
                client_name = excluded.client_name,
                property_address = excluded.property_address,
                role = excluded.role,
                assigned_agent = excluded.assigned_agent,
                metadata_json = excluded.metadata_json
        """, (
            client_id,
            client_name,
            property_address,
            role,
            assigned_agent,
            json.dumps(metadata or {})
        ))
        self.conn.commit()

    def record_drawer_file(
        self,
        client_id: str,
        agent_id: str,
        category: str,
        filename: str,
        file_path: str,
        file_hash: str,
        size_bytes: int
    ) -> int:
        """Indexes an artifact or document in the client's drawer."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO client_drawer_files
            (client_id, agent_id, category, filename, file_path, file_hash, size_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (client_id, agent_id, category, filename, file_path, file_hash, size_bytes))
        self.conn.commit()
        return cursor.lastrowid

    def get_drawer_files(self, client_id: str, category: Optional[str] = None) -> list[dict]:
        """Retrieves all files indexed for a specific client drawer."""
        cursor = self.conn.cursor()
        if category:
            cursor.execute("""
                SELECT id, agent_id, category, filename, file_path, file_hash, size_bytes, created_at
                FROM client_drawer_files
                WHERE client_id = ? AND category = ?
                ORDER BY id ASC
            """, (client_id, category))
        else:
            cursor.execute("""
                SELECT id, agent_id, category, filename, file_path, file_hash, size_bytes, created_at
                FROM client_drawer_files
                WHERE client_id = ?
                ORDER BY id ASC
            """, (client_id,))
        rows = cursor.fetchall()
        return [
            {
                "id": r["id"],
                "agent_id": r["agent_id"],
                "category": r["category"],
                "filename": r["filename"],
                "file_path": r["file_path"],
                "file_hash": r["file_hash"],
                "size_bytes": r["size_bytes"],
                "created_at": r["created_at"]
            }
            for r in rows
        ]

    def list_client_drawers(self) -> list[dict]:
        """Lists all registered client drawers with file counts."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT d.client_id, d.client_name, d.property_address, d.role, d.assigned_agent,
                   d.created_at, COUNT(f.id) as file_count
            FROM client_drawers d
            LEFT JOIN client_drawer_files f ON d.client_id = f.client_id
            GROUP BY d.client_id
            ORDER BY d.created_at DESC
        """)
        rows = cursor.fetchall()
        return [
            {
                "client_id": r["client_id"],
                "client_name": r["client_name"],
                "property_address": r["property_address"],
                "role": r["role"],
                "assigned_agent": r["assigned_agent"],
                "created_at": r["created_at"],
                "file_count": r["file_count"]
            }
            for r in rows
        ]
