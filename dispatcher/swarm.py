"""swarm - builds the whole ListingAssistants swarm in one place.

Added 2026-10-11. Before this the console, the daily-clock CLI and the MCP
server each built their own hub and agents, and the clock CLI built an
EMPTY swarm (it could restore nothing), so a cron-run sweep found no
deadlines to check. Every operator entry point now builds through here:

    sw = build_swarm(audit_path, state_db=..., config_dir=..., verifier=...)
    sw.hub.send(...)            # everything goes through the dispatcher
    sw.save_state()             # after a session / sweep run

What it wires
  - the hub on the closed track (identity/routes.json) and the audit log
  - all twenty agents (the vendor roster for 09 from <config_dir>/
    vendor_panel.json, only when ratified - the verdict lands on the log)
  - the HITL manager as hub.hitl: every "hold for a human, continue or
    cancel" decision goes through it (signed hitl.decision.authority)
  - the SQLite store (state_db): the swarm's state is restored at start-up
    and saved by save_state(); see dispatcher/state_snapshot.py for the
    integrity rules. state_db=None keeps state in this process only, and
    the audit log says so (state.ephemeral).
  - the plain-language log (added 2026-10-12): the hub's audit log is a
    ReadableAuditLog, so every chain entry also lands, described, in
    <readable_dir>/stream.log (default: "readable" next to the audit log);
    write_eod() builds the end-of-day ledger from the chain.
"""
from __future__ import annotations

import datetime
import os
from typing import Any, Callable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Swarm:
    def __init__(self, hub, spokes, hitl, store, external, baseline, roster_info):
        self.hub = hub
        self.spokes = spokes
        self.hitl = hitl
        self.store = store
        self.external = external
        self.baseline = baseline
        self.roster_info = roster_info
        self.restored: Optional[dict] = None
        self.readable = None   # set by build_swarm

    def save_state(self) -> Optional[dict]:
        """Saves the swarm's state; returns {snapshot_id, sha256} or None
        when no store is configured."""
        if self.store is None:
            return None
        from . import state_snapshot as ss
        snap = ss.capture(self.hub, self.spokes, self.hitl, self.baseline)
        body, digest = ss.body_and_hash(snap)
        taken = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        sid = self.store.save_state_snapshot(taken, digest, body)
        self.hub.audit.append("state.saved", {"snapshot_id": sid, "sha256": digest,
                                              "taken_at": taken, "bytes": len(body)})
        return {"snapshot_id": sid, "sha256": digest}

    def write_eod(self, date_str: Optional[str] = None) -> dict:
        """End-of-day ledger for the date, built from the chain (every
        session that day), chain verified in its integrity section."""
        from .readable_audit import write_eod
        return write_eod(self.hub.audit, self.readable, date_str)

    def close(self):
        if self.store is not None:
            self.store.close()


def load_roster(config_dir: str):
    """Returns (roster, verdict, problems). Agent 09's format: vendor_id ->
    {kind, license_expiry, insurance_expiry, regulated}. Read only from a
    ratified file; an entry with a missing field or a placeholder is
    skipped and named in problems, never guessed."""
    from .config_status import load_ratified_config
    data, verdict = load_ratified_config(os.path.join(config_dir, "vendor_panel.json"))
    if verdict != "loaded":
        return {}, verdict, []
    vendors = data.get("vendors")
    if not isinstance(vendors, dict):
        return {}, "invalid: no 'vendors' object", []
    roster, problems = {}, []
    for vid, v in vendors.items():
        if vid.startswith("<") or not isinstance(v, dict):
            problems.append(f"{vid}: placeholder or not an object")
            continue
        missing = [k for k in ("kind", "license_expiry", "insurance_expiry")
                   if not isinstance(v.get(k), str) or not v.get(k) or v[k].startswith("<")]
        bad_dates = []
        for k in ("license_expiry", "insurance_expiry"):
            if k not in missing:
                try:
                    datetime.date.fromisoformat(v[k])
                except ValueError:
                    bad_dates.append(k)
        if missing or bad_dates:
            problems.append(f"{vid}: missing {missing}" if missing else f"{vid}: bad date {bad_dates}")
            continue
        roster[vid] = {"kind": v["kind"], "license_expiry": v["license_expiry"],
                       "insurance_expiry": v["insurance_expiry"],
                       "regulated": bool(v.get("regulated", True))}
    return roster, verdict, problems


def build_swarm(audit_path: str, *, state_db: Optional[str] = None,
                config_dir: Optional[str] = None,
                verifier: Optional[Callable] = None,
                human_notifier: Optional[Callable[[str, dict], None]] = None,
                human_sink: Optional[Callable] = None,
                readable_dir: Optional[str] = None,
                drawers_root: Optional[str] = None,
                decision_adapter: Any = None) -> Swarm:
    from .core import Routes, AuditLog
    from .hub import Hub
    from .hitl_protocol import HITLManager
    from . import state_snapshot as ss
    from .listing_spokes import Spoke01LeadCapture, Spoke14CRMPipeline
    from .listing_spokes_02 import Spoke02LeadQualification
    from .listing_spokes_03 import Spoke03LeadNurture
    from .listing_spokes_04 import Spoke04ListingDescription
    from .listing_spokes_05 import Spoke05MLSListingManagement
    from .listing_spokes_06 import Spoke06ShowingScheduler
    from .listing_spokes_07 import Spoke07TransactionCoordinator
    from .listing_spokes_08 import Spoke08DocumentCollection
    from .listing_spokes_09 import Spoke09VendorCoordination
    from .listing_spokes_10 import Spoke10MarketData
    from .listing_spokes_11 import Spoke11ClientCommunication
    from .listing_spokes_12 import Spoke12MarketingCampaign
    from .listing_spokes_13 import Spoke13BuyerSearchMatch
    from .listing_spokes_15 import Spoke15FinancialTracking
    from .listing_spokes_16 import Spoke16AfterCloseReferral
    from .listing_spokes_17 import Spoke17ComplianceFairHousing
    from .listing_spokes_18 import Spoke18CalendarTask
    from .listing_spokes_19 import Spoke19Prospecting
    from .listing_spokes_20 import Spoke20SocialMediaMonitoring

    from .readable_logger import HumanReadableLogger
    from .readable_audit import ReadableAuditLog
    base_dir = os.path.dirname(os.path.abspath(audit_path))
    drawers_root = drawers_root or os.path.join(base_dir, "drawers")
    readable = HumanReadableLogger(log_root=readable_dir or os.path.join(base_dir, "readable"),
                                   drawers_root=drawers_root)
    audit = ReadableAuditLog(audit_path, readable)
    # Check saved state against the chain BEFORE anything is written, so a
    # refusal leaves the log and the store exactly as they were.
    store, row = None, None
    if state_db is not None:
        from .persistence_sqlite import ApplianceStorage
        store = ApplianceStorage(state_db)
        row = store.latest_state_snapshot()
        if row is not None:
            try:
                ss.check_against_chain(audit, row)
            except ss.StateIntegrityError:
                store.close()
                raise
    hub = Hub(Routes(os.path.join(ROOT, "identity", "routes.json")), audit,
              signature_verifier=verifier, human_notifier=human_notifier)
    external: list = []
    hub.register("external", lambda env: external.append(
        {"intent": env.intent, "ctx": env.client_context_id, "payload": env.payload}))
    hub.register("human", human_sink or (lambda env: None))

    from .client_drawer import ClientDrawerManager
    drawers = ClientDrawerManager(drawers_root)
    hub.drawers = drawers   # agents file through dispatcher/drawer_filing.py
    # Agent 02 scores every lead through this adapter (wired 2026-10-12).
    # Default: local engine = 02's rubric; off-box only on a signed opt-in.
    from .decision_adapter import JevDecisionAdapter
    hub.decision_adapter = decision_adapter or JevDecisionAdapter()
    st = hub.decision_adapter.get_coprocessor_status()
    hub.audit.append("decision.engine", {"agent": "swarm", "engine": st.get("mode"),
                                         "tier": None, "confidence": None,
                                         "reason": st.get("reason")})
    hitl = HITLManager(hub=hub, drawer_manager=drawers)
    hub.hitl = hitl   # agents reach it through their guarded hub

    config_dir = config_dir or os.path.join(ROOT, "config")
    roster, verdict, problems = load_roster(config_dir)
    hub.audit.append("config.load", {"agent": "swarm", "file": "vendor_panel.json",
                                     "config_dir": config_dir, "verdict": verdict,
                                     "vendors_loaded": sorted(roster),
                                     "entries_skipped": problems})
    spokes = {
        "01": Spoke01LeadCapture(hub), "02": Spoke02LeadQualification(hub),
        "03": Spoke03LeadNurture(hub), "04": Spoke04ListingDescription(hub),
        "05": Spoke05MLSListingManagement(hub), "06": Spoke06ShowingScheduler(hub),
        "07": Spoke07TransactionCoordinator(hub), "08": Spoke08DocumentCollection(hub),
        "09": Spoke09VendorCoordination(hub, roster=roster), "10": Spoke10MarketData(hub),
        "11": Spoke11ClientCommunication(hub), "12": Spoke12MarketingCampaign(hub),
        "13": Spoke13BuyerSearchMatch(hub), "14": Spoke14CRMPipeline(hub),
        "15": Spoke15FinancialTracking(hub), "16": Spoke16AfterCloseReferral(hub),
        "17": Spoke17ComplianceFairHousing(hub), "18": Spoke18CalendarTask(hub),
        "19": Spoke19Prospecting(hub), "20": Spoke20SocialMediaMonitoring(hub),
    }
    baseline = {aid: ss.encode(ss.agent_state(sp)) for aid, sp in spokes.items()}

    sw = Swarm(hub, spokes, hitl, store, external, baseline,
               {"verdict": verdict, "vendors_loaded": sorted(roster), "entries_skipped": problems})
    sw.readable = readable
    if state_db is None:
        hub.audit.append("state.ephemeral", {
            "reason": "no state store configured - agent state lives in this process only"})
    else:
        if row is None:
            hub.audit.append("state.fresh", {"state_db": state_db})
        else:
            import json
            sw.restored = ss.restore(hub, spokes, hitl, json.loads(row["body"]), baseline)
            hub.audit.append("state.restored", {"snapshot_id": row["id"], "sha256": row["sha256"],
                                                "agents": sorted(a for a, n in sw.restored.items() if n)})
    hub.on_turn_start()
    return sw
