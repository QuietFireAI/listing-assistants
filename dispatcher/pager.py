"""pager - text-message pages for the broker's queue, turned on by the broker.

Owner decision (2026-10-11, #10; J8 2026-10-12): credentials are asked for
when a feature needs them, after onboarding. Before this module the console
said "the Twilio notifier asks for your account credentials when you turn it
on" while nothing could turn it on and nothing asked.

  python tools/console.py pager          # asks for the Twilio details, once
  python tools/console.py pager --test   # sends one test page
  python tools/console.py pager --off    # forgets them

The details are stored in console-state/pager.json, readable by your user
only (mode 0600 on Linux/macOS; on Windows only your account is on the
file's permission list - dispatcher/private_file.py). Every console session then pages you, in addition to printing
on screen, whenever something lands in a human queue.

What a page says: the queue name and the client context id, nothing else -
"ListingAssistants: escalation.hot_lead waiting for you (S3-hot). Open the
console." No client words, names or figures leave the machine in a page.
Every page attempt is on the audit chain (pager.sent / pager.failed) without
the credentials.

The core dispatcher/notifier.py (a vendored dispatcher-agents file) reads its
Twilio settings from environment variables and formats pages with the
client's reason text; this module is the console's own, narrower sender.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

FIELDS = ("account_sid", "auth_token", "from_number", "to_number")
TWILIO_API = "https://api.twilio.com"
_LOCAL = {"localhost", "127.0.0.1", "::1"}


def page_text(queue: str, record: dict) -> str:
    ctx = (record or {}).get("client_context_id") or "no client"
    return f"ListingAssistants: {queue} waiting for you ({ctx}). Open the console."


def validate(cfg: dict) -> list[str]:
    problems = [f"{f} is required" for f in FIELDS if not str(cfg.get(f, "")).strip()]
    for f in ("from_number", "to_number"):
        v = str(cfg.get(f, ""))
        if v and not (v.startswith("+") and v[1:].isdigit() and 8 <= len(v) <= 16):
            problems.append(f"{f} must be an international number like +15551234567")
    base = cfg.get("api_base", TWILIO_API)
    host = urllib.parse.urlparse(base).hostname or ""
    if not (base.startswith("https://") or host in _LOCAL):
        problems.append("api_base must be https (or this machine, for testing)")
    return problems


def save_config(path: str, cfg: dict) -> None:
    from dispatcher.private_file import write_private
    write_private(path, json.dumps(
        {k: cfg[k] for k in (*FIELDS, "api_base") if k in cfg}).encode("utf-8"))


def load_config(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    problems = validate(cfg)
    if problems:
        raise ValueError(f"{path} is not usable: {problems}")
    return cfg


def send_page(cfg: dict, text: str, timeout: float = 10.0,
              opener: Callable = urllib.request.urlopen) -> dict:
    base = cfg.get("api_base", TWILIO_API).rstrip("/")
    url = f"{base}/2010-04-01/Accounts/{cfg['account_sid']}/Messages.json"
    data = urllib.parse.urlencode({"To": cfg["to_number"], "From": cfg["from_number"],
                                   "Body": text}).encode()
    auth = base64.b64encode(f"{cfg['account_sid']}:{cfg['auth_token']}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Authorization": f"Basic {auth}",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(req, timeout=timeout) as resp:  # nosec B310 (scheme checked in validate)
            return {"status": "sent", "http_status": resp.status}
    except urllib.error.HTTPError as e:
        return {"status": "failed", "http_status": e.code}
    except Exception as e:  # reported on the chain, never swallowed
        return {"status": "failed", "error": f"{type(e).__name__}: {e}"}


class Pager:
    """human_notifier add-on: pages, and records each attempt on the chain."""

    def __init__(self, cfg: dict, opener: Callable = urllib.request.urlopen):
        self.cfg = cfg
        self.opener = opener
        self.audit: Any = None   # set once the swarm exists

    def __call__(self, queue: str, record: dict) -> dict:
        res = send_page(self.cfg, page_text(queue, record), opener=self.opener)
        if self.audit is not None:
            self.audit.append("pager.sent" if res["status"] == "sent" else "pager.failed",
                              {"queue": queue,
                               "client_context_id": (record or {}).get("client_context_id"),
                               **{k: v for k, v in res.items() if k != "status"}})
        return res
