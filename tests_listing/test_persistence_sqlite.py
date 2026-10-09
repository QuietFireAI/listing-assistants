"""Tests for appliance SQLite persistence layer."""
import os
import tempfile
import pytest
from dispatcher.persistence_sqlite import ApplianceStorage


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
            amount=500_000.0,
            commission_rate=0.06,
            balance=30_000.0,
            payload={"split": "50/50"}
        )
        history = storage.get_financial_history("ctx-fin")
        assert len(history) == 1
        assert history[0]["amount"] == 500_000.0
        assert history[0]["commission_rate"] == 0.06
        assert history[0]["balance"] == 30_000.0


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
