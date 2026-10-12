"""Tests for Human-Readable Logging Stream, EOD Ledger, and Client Funnel Dashboard."""
import os
import tempfile
import pytest
from dispatcher.readable_logger import HumanReadableLogger
from dispatcher.client_drawer import ClientDrawerManager
from tools.dashboard import load_all_clients, determine_client_stage, render_html_dashboard


def test_human_readable_logger_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = os.path.join(tmpdir, "logs")
        drawers_dir = os.path.join(tmpdir, "drawers")
        
        # Provision a client drawer
        drawer_mgr = ClientDrawerManager(drawers_dir)
        drawer = drawer_mgr.provision_drawer("ctx-seller-888", "Jane Seller", "888 Vine St")
        
        logger = HumanReadableLogger(log_root=log_dir, drawers_root=drawers_dir)
        
        # 1. Log real-time events
        logger.log_dispatch("01", "02", "lead.signal", "ctx-seller-888", "New lead from web portal")
        logger.log_decision("02", "ctx-seller-888", "JEV AI Engine", "Tier: WARM (Score: 65)")
        logger.log_vault_action("ctx-seller-888", "04", "Stored copy draft", "listing_copy.md", "sha256abc123")
        logger.log_api_attempt("Twilio", "/Messages.json", "201 OK", "+1-555-555-0100", "SMS delivered")
        logger.log_alert("DECISION_REQUIRED", "ctx-seller-888", "Boundary score 70.0 escalated", "SMS")
        
        # Verify master stream file written
        assert os.path.exists(logger.stream_path)
        with open(logger.stream_path, "r", encoding="utf-8") as f:
            stream_content = f.read()
            assert "DISPATCH" in stream_content
            assert "JEV AI Engine" in stream_content
            assert "Twilio" in stream_content
            
        # Verify client drawer activity log written
        client_log = os.path.join(drawers_dir, "ctx-seller-888", "audit", "activity.log")
        assert os.path.exists(client_log)
        with open(client_log, "r", encoding="utf-8") as f:
            client_content = f.read()
            assert "New lead from web portal" in client_content
            
        # 2. Generate EOD report
        report = logger.generate_eod_report()
        assert report["total_events"] == 5
        assert report["breakdown"]["DISPATCH"] == 1
        assert report["breakdown"]["DECISION"] == 1
        assert os.path.exists(report["report_file"])
        assert "End-of-Day" in report["markdown"]


def test_dashboard_funnel_and_html_generation():
    with tempfile.TemporaryDirectory() as tmpdir:
        drawers_dir = os.path.join(tmpdir, "drawers")
        drawer_mgr = ClientDrawerManager(drawers_dir)
        
        # Provision client
        drawer = drawer_mgr.provision_drawer("ctx-buyer-555", "Charlie Buyer", "555 Pine Rd", role="buyer")
        drawer.store_file("04", "documents", "listing_copy_v1.md", "Beautiful home...")
        
        clients = load_all_clients(drawers_dir)
        assert len(clients) == 1
        c = clients[0]
        assert c["client_name"] == "Charlie Buyer"
        assert c["property_address"] == "555 Pine Rd"
        assert c["role"] == "Buyer"
        assert "PRE-MARKET" in c["stage_name"]
        
        # Render HTML
        out_html = os.path.join(tmpdir, "test_dashboard.html")
        render_html_dashboard(clients, out_html)
        assert os.path.exists(out_html)
        with open(out_html, "r", encoding="utf-8") as f:
            html = f.read()
            assert "Charlie Buyer" in html
            assert "555 Pine Rd" in html
            assert "PRE-MARKET" in html


def test_eod_integrity_is_computed_or_labeled_not_computed(tmp_path):
    """Was: fixed text "hash chaining active", "0 cross-drawer breaches",
    "0 unauthorized wire routing transmissions" printed with nothing computed."""
    from dispatcher.core import AuditLog
    logger = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=None)
    logger.log_event("DISPATCH", "x")
    md = logger.generate_eod_report()["markdown"]
    assert "hash chaining active" not in md and "0 cross-drawer" not in md and "0 unauthorized" not in md
    assert "Audit chain:** not computed" in md and "Wire transmissions:** not computed" in md

    audit = AuditLog(str(tmp_path / "audit.jsonl"))
    audit.append("send", {"a": 1})
    audit.append("integrity.violation", {"b": 2})
    rep = logger.generate_eod_report(audit_log=audit)
    assert "verified, 2 entries" in rep["markdown"] and rep["integrity"]["integrity_violations"] == 1

    lines = open(audit.path, encoding="utf-8").read().splitlines()
    lines[0] = lines[0].replace('"a": 1', '"a": 9')
    open(audit.path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    assert "BROKEN at line 1" in logger.generate_eod_report(audit_log=AuditLog(audit.path))["markdown"]


def test_unsafe_client_id_is_not_joined_into_a_path(tmp_path):
    drawers = tmp_path / "drawers"
    (drawers / "victim").mkdir(parents=True)
    logger = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=str(drawers / "sub"))
    (drawers / "sub").mkdir()
    logger.log_event("NOTE", "escape attempt", client_context_id="../victim")
    assert not (drawers / "victim" / "audit").exists()
    assert "skipped" in logger.session_events[-1]["details"]["drawer_copy"]


def test_eod_for_a_day_with_no_events_reports_zero(tmp_path):
    logger = HumanReadableLogger(log_root=str(tmp_path / "logs"), drawers_root=None)
    logger.log_event("DISPATCH", "today")
    assert logger.generate_eod_report(date_str="1999-01-01")["total_events"] == 0
