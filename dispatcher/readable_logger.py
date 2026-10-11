"""readable_logger - plain-language event log and end-of-day (EOD) report.

  1. Stream: every log_* call appends one line to logs/stream.log.
  2. Per-client copy: events with a client_context_id are also appended to
     drawers/<client_id>/audit/activity.log when that drawer exists.
  3. EOD report: counts the events logged in this process for a date and
     writes logs/daily/eod_ledger_<date>.md.

What gets logged is whatever code calls these methods. Today the callers are
the Hermes learning loop, the checkpoint manager and the tools; the hub and
the 20 spokes write to the hash-chained AuditLog, not to this logger.

Fixed 2026-10-11 (audit LOG-1, D-4):
  - The EOD "integrity" section printed fixed text ("hash chaining active",
    "0 cross-drawer breaches", "0 unauthorized wire transmissions") that
    nothing computed. It now verifies the AuditLog chain when one is passed
    and labels every other line "not computed".
  - A client_context_id that is not a safe path segment is no longer joined
    into a filesystem path; the event stays in the stream with a note.
  - A date with no events reports 0 events instead of silently reporting
    every event in the session under that date.
"""
from __future__ import annotations

import datetime
import os
import re
from typing import Any, Optional

# same rule as dispatcher/client_drawer.py _SEGMENT
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class HumanReadableLogger:
    """Provides human-friendly real-time logging and end-of-day summary reports."""

    def __init__(self, log_root: str = "logs", drawers_root: Optional[str] = "drawers"):
        self.log_root = os.path.abspath(log_root)
        self.drawers_root = os.path.abspath(drawers_root) if drawers_root else None
        os.makedirs(self.log_root, exist_ok=True)
        os.makedirs(os.path.join(self.log_root, "daily"), exist_ok=True)
        self.stream_path = os.path.join(self.log_root, "stream.log")
        self.session_events: list[dict] = []

    def _now_str(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _today_str(self) -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d")

    def log_event(
        self,
        category: str,
        message: str,
        client_context_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        details: Optional[dict] = None
    ) -> str:
        """Logs a single real-time operational event in clean human-readable prose."""
        ts = self._now_str()
        cat_tag = f"[{category.upper()}]"
        agent_tag = f"[Agent {agent_id}]" if agent_id else ""
        client_tag = f"[Client: {client_context_id}]" if client_context_id else ""
        
        line = f"[{ts}] {cat_tag:<16} {agent_tag:<11} {client_tag:<24} {message}"
        
        # Write to master stream log
        with open(self.stream_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

        # Record in memory for EOD ledger
        event_rec = {
            "timestamp": ts,
            "category": category,
            "agent_id": agent_id,
            "client_context_id": client_context_id,
            "message": message,
            "details": details or {}
        }
        self.session_events.append(event_rec)

        # Write to client drawer activity log if drawer exists. The id must be
        # a safe single path segment before it is joined into a path.
        if client_context_id and self.drawers_root and not _SAFE_SEGMENT.match(str(client_context_id)):
            event_rec["details"]["drawer_copy"] = "skipped: client_context_id is not a safe path segment"
        elif client_context_id and self.drawers_root:
            client_drawer_dir = os.path.join(self.drawers_root, client_context_id)
            if os.path.exists(client_drawer_dir):
                client_audit_dir = os.path.join(client_drawer_dir, "audit")
                os.makedirs(client_audit_dir, exist_ok=True)
                client_log = os.path.join(client_audit_dir, "activity.log")
                with open(client_log, "a", encoding="utf-8") as cf:
                    cf.write(f"[{ts}] {cat_tag:<14} {agent_tag:<10} {message}\n")

        return line

    def log_dispatch(self, from_agent: str, to_agent: str, intent: str, client_context_id: str, summary: str = ""):
        msg = f"Dispatched '{intent}' to Agent {to_agent}."
        if summary:
            msg += f" {summary}"
        return self.log_event("DISPATCH", msg, client_context_id=client_context_id, agent_id=from_agent)

    def log_decision(self, agent_id: str, client_context_id: str, engine: str, verdict: str, details: Optional[dict] = None):
        msg = f"Decision rendered via {engine}: {verdict}"
        return self.log_event("DECISION", msg, client_context_id=client_context_id, agent_id=agent_id, details=details)

    def log_vault_action(self, client_context_id: str, agent_id: str, action: str, filepath: str, sha256_hash: str = ""):
        hash_short = f" (SHA: {sha256_hash[:12]}...)" if sha256_hash else ""
        msg = f"{action}: {os.path.basename(filepath)}{hash_short}"
        return self.log_event("VAULT", msg, client_context_id=client_context_id, agent_id=agent_id)

    def log_api_attempt(self, service: str, endpoint: str, status: str, recipient: str = "", note: str = ""):
        recip_str = f" to {recipient}" if recipient else ""
        note_str = f" - {note}" if note else ""
        msg = f"API call to {service} [{endpoint}]{recip_str} -> Status: {status}{note_str}"
        return self.log_event("API_CALL", msg)

    def log_alert(self, alert_type: str, client_context_id: str, reason: str, channel: str = "SMS"):
        msg = f"High-priority alert fired via {channel}: {reason}"
        return self.log_event("ALERT", msg, client_context_id=client_context_id)

    def log_training_update(self, agent_id: str, client_context_id: str, topic: str, variance: float, status: str, detail: str = ""):
        msg = f"Hermes Learning Loop [{topic}]: Variance={variance:.4f} -> Status: {status}"
        if detail:
            msg += f" | {detail}"
        cat = "TRAIN_UPDATE" if status.startswith("ASSIMILATED") else "TRAIN_ALERT"
        return self.log_event(cat, msg, client_context_id=client_context_id, agent_id=agent_id,
                              details={"topic": topic, "variance": variance, "status": status})

    def generate_eod_report(self, date_str: Optional[str] = None, audit_log: Any = None) -> dict:
        """Builds the EOD report from events logged in this process on the date.
        Pass the hub's AuditLog as audit_log to have its hash chain verified
        in section 4; without it, section 4 says "not computed"."""
        target_date = date_str or self._today_str()
        events = [e for e in self.session_events if e["timestamp"].startswith(target_date)]

        by_cat: dict[str, int] = {}
        by_client: dict[str, int] = {}
        for ev in events:
            cat = ev["category"]
            by_cat[cat] = by_cat.get(cat, 0) + 1
            cid = ev.get("client_context_id")
            if cid:
                by_client[cid] = by_client.get(cid, 0) + 1

        report_lines = [
            f"# ListingAssistants End-of-Day (EOD) Operations Ledger",
            f"**Date:** {target_date}  ",
            f"**Generated:** {self._now_str()}  ",
            f"**Total Operational Steps Logged:** {len(events)}  ",
            "",
            "## 1. Daily Activity Breakdown",
            "| Event Category | Operations Count | Description |",
            "|---|---|---|",
            f"| **DISPATCH** | {by_cat.get('DISPATCH', 0)} | Closed-track spoke envelopes routed through Hub |",
            f"| **DECISION** | {by_cat.get('DECISION', 0)} | Decisions recorded via log_decision |",
            f"| **VAULT** | {by_cat.get('VAULT', 0)} | Client drawer file actions recorded via log_vault_action |",
            f"| **API_CALL** | {by_cat.get('API_CALL', 0)} | External call attempts recorded via log_api_attempt |",
            f"| **ALERT** | {by_cat.get('ALERT', 0)} | Alerts recorded via log_alert |",
            "",
            "## 2. Client Drawer Activity Volume",
            "| Client Context ID | Total Touches & Artifacts |",
            "|---|---|"
        ]
        if by_client:
            for cid, count in by_client.items():
                report_lines.append(f"| `{cid}` | {count} steps |")
        else:
            report_lines.append("| *(No client-specific touches recorded)* | 0 |")

        report_lines.extend([
            "",
            "## 3. Chronological Operational Event Stream",
            "```text"
        ])
        for ev in events[-50:]:  # last 50 events in detail
            report_lines.append(f"[{ev['timestamp']}] [{ev['category']:<9}] {ev.get('message')}")
        integrity = self._integrity_section(audit_log)
        report_lines.extend(["```", "", "## 4. Audit Integrity"] + integrity["lines"])

        md_content = "\n".join(report_lines)
        report_file = os.path.join(self.log_root, "daily", f"eod_ledger_{target_date}.md")
        with open(report_file, "w", encoding="utf-8") as rf:
            rf.write(md_content)

        return {
            "date": target_date,
            "report_file": report_file,
            "total_events": len(events),
            "breakdown": by_cat,
            "integrity": integrity["data"],
            "markdown": md_content
        }

    @staticmethod
    def _integrity_section(audit_log: Any) -> dict:
        if audit_log is None or not hasattr(audit_log, "verify_chain"):
            chain_line = "- **Audit chain:** not computed (no audit log was passed to this report)."
            data: dict = {"chain": None}
        else:
            chain = audit_log.verify_chain()
            kinds: dict[str, int] = {}
            for e in audit_log.read():
                kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
            if chain["ok"]:
                chain_line = f"- **Audit chain:** verified, {chain['entries']} entries, no break."
            else:
                chain_line = f"- **Audit chain:** BROKEN at line {chain['break_at']}."
            data = {"chain": chain, "integrity_violations": kinds.get("integrity.violation", 0),
                    "rejects": kinds.get("reject", 0)}
            chain_line += (f" integrity.violation entries: {data['integrity_violations']};"
                           f" reject entries: {data['rejects']}.")
        return {"data": data, "lines": [
            chain_line,
            "- **Cross-drawer access:** not computed (ClientDrawerManager refuses at the call site; "
            "refusals are not counted here).",
            "- **Wire transmissions:** not computed (no wire-transmission monitor exists).",
        ]}


# Global singleton logger instance
_GLOBAL_LOGGER: Optional[HumanReadableLogger] = None

def get_readable_logger() -> HumanReadableLogger:
    global _GLOBAL_LOGGER
    if _GLOBAL_LOGGER is None:
        _GLOBAL_LOGGER = HumanReadableLogger()
    return _GLOBAL_LOGGER
