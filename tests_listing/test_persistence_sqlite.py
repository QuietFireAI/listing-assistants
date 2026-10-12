"""Tests for appliance SQLite persistence layer."""
import os
import sqlite3
import tempfile
from decimal import Decimal

import pytest
from dispatcher.persistence_sqlite import ApplianceStorage, DrawerIdentityConflict, SchemaMismatch


def test_sqlite_crm_operations():
    with ApplianceStorage(":memory:") as storage:
        # Record interactions
        storage.record_crm_interaction("ctx-001", "11", "client_touch", {"template": "welcome"})
        storage.record_crm_interaction("ctx-001", "14", "note", {"text": "client preferred sms"})

        interactions = storage.get_crm_interactions("ctx-001")
        assert len(interactions) == 2
        assert interactions[0]["kind"] == "client_touch"
        assert interactions[1]["payload"]["text"] == "client preferred sms"

        # Test consent management
        assert storage.get_client_consent("ctx-001") == {}
        storage.update_client_consent("ctx-001", {"sms": "yes", "email": "yes"})
        assert storage.get_client_consent("ctx-001") == {"sms": "yes", "email": "yes"}

        # Update one channel
        storage.update_client_consent("ctx-001", {"phone": "no"})
        assert storage.get_client_consent("ctx-001") == {"sms": "yes", "email": "yes", "phone": "no"}


def test_sqlite_financial_ledger_operations():
    with ApplianceStorage(":memory:") as storage:
        storage.record_financial_entry(
            client_context_id="ctx-fin",
            event_type="commission_calculated",
            amount=500_000,
            commission_rate="0.06",
            balance=Decimal("30000.00"),
            payload={"split": "50/50"}
        )
        history = storage.get_financial_history("ctx-fin")
        assert len(history) == 1
        assert history[0]["amount"] == Decimal("500000")
        assert history[0]["commission_rate"] == Decimal("0.06")
        assert history[0]["balance"] == Decimal("30000.00")


def test_money_is_exact_and_floats_are_refused():
    """Was REAL: 0.1 + 0.2 summed to 0.30000000000000004 (probe_sqlite.py)."""
    with ApplianceStorage(":memory:") as s:
        s.record_financial_entry("c1", "commission", amount="0.1")
        s.record_financial_entry("c1", "commission", amount=Decimal("0.2"))
        assert sum(e["amount"] for e in s.get_financial_history("c1")) == Decimal("0.3")
        with pytest.raises(TypeError):
            s.record_financial_entry("c1", "commission", amount=0.1)
        with pytest.raises(ValueError):
            s.record_financial_entry("c1", "commission", amount="ten dollars")
        with pytest.raises(ValueError):
            s.record_financial_entry("c1", "commission", amount="NaN")


def test_ledgers_are_append_only():
    with ApplianceStorage(":memory:") as s:
        s.record_crm_interaction("c1", "14", "note", {"t": 1})
        s.record_financial_entry("c1", "commission", amount="100.00")
        s.update_client_consent("c1", {"sms": "yes"})
        s.record_drawer_file("c1", "04", "artifacts", "a.txt", "/x/a.txt", "ab" * 32, 3)
        for table in ("crm_interactions", "financial_ledger", "client_consent_events", "client_drawer_files"):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                s.conn.execute(f"UPDATE {table} SET id = id")
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                s.conn.execute(f"DELETE FROM {table}")


def test_consent_history_is_kept():
    with ApplianceStorage(":memory:") as s:
        s.update_client_consent("c1", {"sms": "opted_out"}, source="client email 2026-10-01")
        s.update_client_consent("c1", {"sms": "opted_in"}, source="client call 2026-10-05")
        # owner decision 2026-10-11: re-opt-in after opt-out needs a human
        assert s.get_client_consent("c1") == {"sms": "opted_out"}
        assert s.get_pending_consent("c1") == {"sms": "opted_in"}
        hist = s.get_consent_history("c1")
        assert [(h["value"], h["source"], h["status"]) for h in hist] == [
            ("opted_out", "client email 2026-10-01", "effective"),
            ("opted_in", "client call 2026-10-05", "pending_confirmation")]
        with pytest.raises(ValueError):
            s.confirm_consent("c1", "sms", "")
        assert s.confirm_consent("c1", "sms", "broker J. Phillips") is True
        assert s.get_client_consent("c1") == {"sms": "opted_in"} and s.get_pending_consent("c1") == {}
        assert s.confirm_consent("c1", "sms", "broker") is False         # nothing pending
        s.update_client_consent("c1", {"email": "yes"})                    # first-time opt-in: effective
        assert s.get_client_consent("c1")["email"] == "yes"
        with pytest.raises(ValueError):
            s.update_client_consent("c1", {})


def test_drawer_identity_never_silently_overwritten():
    """Was: second register replaced Alice/1 Oak with Mallory/9 Elm."""
    with ApplianceStorage(":memory:") as s:
        s.register_client_drawer("c1", "Alice", "1 Oak")
        s.register_client_drawer("c1", "Alice", "1 Oak")             # same identity: no-op
        with pytest.raises(DrawerIdentityConflict):
            s.register_client_drawer("c1", "Mallory", "9 Elm")
        assert s.list_client_drawers()[0]["client_name"] == "Alice"
        s.register_client_drawer("c1", "Alice Smith", "1 Oak", update_identity=True)
        assert s.list_client_drawers()[0]["client_name"] == "Alice Smith"
        assert [h["client_name"] for h in s.get_drawer_identity_history("c1")] == ["Alice"]


def test_wal_mode_and_schema1_file_refused(tmp_path):
    db = str(tmp_path / "a.db")
    with ApplianceStorage(db) as s:
        assert s.journal_mode == "wal"
    old = str(tmp_path / "old.db")
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE financial_ledger (id INTEGER PRIMARY KEY, amount REAL)")
    con.commit(); con.close()
    with pytest.raises(SchemaMismatch):
        ApplianceStorage(old)


def test_sqlite_persistence_on_disk():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_appliance.db")
        # Write state
        with ApplianceStorage(db_file) as s1:
            s1.record_crm_interaction("ctx-disk", "11", "touch", {"status": "ok"})
            s1.update_client_consent("ctx-disk", {"email": "yes"})

        # Reopen state (simulate appliance reboot)
        with ApplianceStorage(db_file) as s2:
            history = s2.get_crm_interactions("ctx-disk")
            assert len(history) == 1
            assert history[0]["payload"]["status"] == "ok"
            assert s2.get_client_consent("ctx-disk") == {"email": "yes"}


# --- added after the post-fix mutation run (2026-10-11) ----------------------

def test_drawer_files_filter_by_category():
    with ApplianceStorage(":memory:") as s:
        s.record_drawer_file("c1", "04", "artifacts", "a.md", "/x/a.md", "a" * 64, 1)
        s.record_drawer_file("c1", "08", "documents", "d.pdf", "/x/d.pdf", "b" * 64, 2)
        s.record_drawer_file("c2", "04", "artifacts", "z.md", "/x/z.md", "c" * 64, 3)
        assert [f["filename"] for f in s.get_drawer_files("c1")] == ["a.md", "d.pdf"]
        assert [f["filename"] for f in s.get_drawer_files("c1", "documents")] == ["d.pdf"]
        assert s.get_drawer_files("c1", "financials") == []


def test_error_messages_name_the_field_and_value():
    with ApplianceStorage(":memory:") as s:
        assert s.journal_mode == "memory"
        with pytest.raises(TypeError, match="^commission_rate: pass Decimal, int or a decimal string, not float"):
            s.record_financial_entry("c1", "x", commission_rate=0.03)
        with pytest.raises(ValueError, match="^balance: 'abc' is not a decimal number"):
            s.record_financial_entry("c1", "x", balance="abc")
        with pytest.raises(ValueError, match="^amount: 'Infinity' is not finite"):
            s.record_financial_entry("c1", "x", amount="Infinity")
        with pytest.raises(ValueError, match="confirmed_by is required"):
            s.confirm_consent("c1", "sms", "")


def test_schema_version_mismatch_and_schema1_messages(tmp_path):
    db = str(tmp_path / "v.db")
    ApplianceStorage(db).close()
    con = sqlite3.connect(db)
    con.execute("UPDATE schema_meta SET value = '99' WHERE key = 'version'")
    con.commit(); con.close()
    with pytest.raises(SchemaMismatch, match="schema version 99, expected 3"):
        ApplianceStorage(db)
    old = str(tmp_path / "old.db")
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE client_consent (client_context_id TEXT)")
    con.commit(); con.close()
    with pytest.raises(SchemaMismatch, match="schema-1 store"):
        ApplianceStorage(old)


def test_close_releases_the_connection(tmp_path):
    s = ApplianceStorage(str(tmp_path / "c.db"))
    s.close()
    assert s.conn is None
    s.close()                                         # idempotent


def test_triggers_are_named_per_operation():
    with ApplianceStorage(":memory:") as s:
        names = {r[0] for r in s.conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert "financial_ledger_no_update" in names and "financial_ledger_no_delete" in names
