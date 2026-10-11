"""Audit 2026-10-11 (CFG-1, CFG-2): identity configs load only when ratified,
and every load verdict is declared on the audit log."""
import json
import os

import pytest

from dispatcher.config_status import is_ratified, load_ratified_config
from dispatcher.core import Routes, AuditLog
from dispatcher.hub import Hub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("status,expected", [
    ("RATIFIED 2026-07-17 (owner decision #3)", True),
    ("PROPOSED DRAFT ... | ALL TEMPLATES RATIFIED Jeff Phillips 2026-07-18", True),
    ("UNRATIFIED TEMPLATE - owner must edit, ratify (date + sign-off)", False),
    ("PROPOSED DRAFT - loads fail closed while status is not RATIFIED. wired 2026-07-17", False),
    ("RATIFIED", False),          # no date = not a ratification record
    (None, False), ("", False),
])
def test_is_ratified_rule(status, expected):
    assert is_ratified(status) is expected


def test_repo_configs_ratification_state_is_what_the_files_say():
    got = {f: is_ratified(json.load(open(os.path.join(ROOT, "config", f))).get("_status"))
           for f in sorted(os.listdir(os.path.join(ROOT, "config")))}
    assert got == {
        "authority_signers.json": False, "cadence_settings.json": False,
        "description_cut_priority.json": True, "integrations_template.json": False,
        "message_templates.json": True, "milestone_map.json": False,
        "transaction_milestones.json": False, "vendor_panel.json": False}


def test_bad_json_is_reported_not_swallowed(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{not json")
    data, verdict = load_ratified_config(str(p))
    assert data is None and verdict.startswith("invalid:")


def _hub(tmp_path):
    return Hub(Routes(os.path.join(ROOT, "identity", "routes.json")),
               AuditLog(os.path.join(str(tmp_path), "a.jsonl")))


def test_spokes_07_08_declare_unratified_draft_and_keep_defaults(tmp_path):
    from dispatcher.listing_spokes_07 import Spoke07TransactionCoordinator
    from dispatcher.listing_spokes_08 import Spoke08DocumentCollection
    hub = _hub(tmp_path)
    s7 = Spoke07TransactionCoordinator(hub)
    s8 = Spoke08DocumentCollection(hub)
    loads = {e["agent"]: e["verdict"] for e in hub.audit.read() if e["kind"] == "config.load"}
    assert loads == {"07": "unratified", "08": "unratified"}
    assert s7.transaction_milestone_config == Spoke07TransactionCoordinator._DEFAULT_TRANSACTION_MILESTONES
    assert s8.document_chase_cap == 3


def test_spoke_10_has_no_untupled_subject_mode():
    """The Gemini-added data.request mode='subject' returned before tuple 3's
    opinion gate and had no decision tuple; it was removed (nothing sent it)."""
    import dispatcher.listing_spokes_10 as m
    assert '== "subject"' not in open(m.__file__).read()
