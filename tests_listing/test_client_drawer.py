"""Tests for Client Drawer Management, Client Isolation, and Anti-Commingling Guards."""
import os
import tempfile
import pytest
from dispatcher.client_drawer import ClientDrawerManager, ComminglingBreachError
from dispatcher.persistence_sqlite import ApplianceStorage


def test_client_drawer_provisioning_and_isolation():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ClientDrawerManager(tmpdir)

        # 1. Provision Drawer for Client A
        drawer_a = manager.provision_drawer(
            client_id="client-smith-01",
            client_name="John & Mary Smith",
            property_address="742 Evergreen Terrace",
            role="seller",
            assigned_agent="00"
        )
        assert os.path.exists(os.path.join(tmpdir, "client-smith-01"))
        manifest = drawer_a.get_manifest()
        assert manifest["client_name"] == "John & Mary Smith"
        assert manifest["property_address"] == "742 Evergreen Terrace"

        # 2. Provision Drawer for Client B
        drawer_b = manager.provision_drawer(
            client_id="client-jones-02",
            client_name="Alice Jones",
            property_address="123 Maple Street",
            role="buyer",
            assigned_agent="00"
        )
        assert os.path.exists(os.path.join(tmpdir, "client-jones-02"))

        # 3. Agents store files in Client A's drawer
        file_a = manager.record_agent_artifact(
            client_id="client-smith-01",
            agent_id="04",
            category="artifacts",
            filename="mls_remarks.txt",
            content="Stunning 4BR home on quiet cul-de-sac."
        )
        assert os.path.exists(file_a)

        # 4. Agent 08 files disclosure in Client A's drawer
        file_disc = manager.record_agent_artifact(
            client_id="client-smith-01",
            agent_id="08",
            category="documents",
            filename="property_disclosure.pdf",
            content=b"%PDF-1.4 Mock Disclosure Bytes"
        )
        assert os.path.exists(file_disc)

        # 5. Verify Client B's drawer has NO files from Client A (Anti-Commingling)
        files_b = drawer_b.list_files()
        assert len(files_b) == 0, "Client B's drawer must be completely isolated and empty"

        # 6. Verify Client A has exactly 2 files
        files_a = drawer_a.list_files()
        assert len(files_a) == 2
        categories = {f["category"] for f in files_a}
        assert "artifacts" in categories
        assert "documents" in categories


def test_anti_commingling_breach_prevention():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = ClientDrawerManager(tmpdir)
        manager.provision_drawer(
            client_id="client-legit",
            client_name="Legit Seller",
            property_address="100 Main St"
        )

        # Attempt to file an artifact for an unprovisioned client must FAIL CLOSED
        with pytest.raises(ComminglingBreachError) as exc_info:
            manager.record_agent_artifact(
                client_id="client-unregistered-spoof",
                agent_id="11",
                category="interactions",
                filename="unauth_chat.txt",
                content="Trying to drop file without drawer"
            )
        assert "blocked fail-closed" in str(exc_info.value)


def test_client_drawer_sqlite_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        with ApplianceStorage(db_path) as storage:
            # Register drawers in SQLite
            storage.register_client_drawer(
                client_id="c-001",
                client_name="Robert Johnson",
                property_address="500 Elm Street",
                role="seller",
                assigned_agent="00"
            )
            storage.register_client_drawer(
                client_id="c-002",
                client_name="Sarah Connor",
                property_address="2024 Skynet Way",
                role="buyer",
                assigned_agent="00"
            )

            # Record files
            storage.record_drawer_file(
                client_id="c-001",
                agent_id="04",
                category="artifacts",
                filename="mls_draft.txt",
                file_path="/mnt/drawers/c-001/artifacts/mls_draft.txt",
                file_hash="abc123hash",
                size_bytes=1024
            )

            # Check files for c-001
            files_c1 = storage.get_drawer_files("c-001")
            assert len(files_c1) == 1
            assert files_c1[0]["filename"] == "mls_draft.txt"

            # Check files for c-002 (must be 0, no commingling)
            files_c2 = storage.get_drawer_files("c-002")
            assert len(files_c2) == 0

            # List drawers
            drawers = storage.list_client_drawers()
            assert len(drawers) == 2
            c1_entry = next(d for d in drawers if d["client_id"] == "c-001")
            assert c1_entry["file_count"] == 1
