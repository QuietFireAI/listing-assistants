"""alert_door - the one door through which a text message leaves the box.

Agent isolation V1 (owner decisions 2026-10-26): the dispatcher has no
internet. When it must reach you (an agent stopped, anything landing in a
queue for you with the pager on), it asks this door, over the same kind of
portal line the agents use, with a fixed menu of one item:

    page(queue, client_context_id, alert_code, system_id, agent)

The door builds the text itself from those fields (dispatcher/pager.py,
page_text) after checking each is a short plain code, so nothing else can
leave through it: no client names, no words, no figures, even if the
dispatcher were tampered with. The Twilio details live only in the door's
own folder; the dispatcher never holds them.

    python -m dispatcher.alert_door serve <socket path> <pager.json>
    python -m dispatcher.alert_door setup <pager.json>      # asks once, sends a test
"""
from __future__ import annotations

import os
import re
import socket
import sys
from typing import Any, Optional

FIELD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\-]{0,63}$")


def _field(name: str, value: Any, required: bool = False) -> Optional[str]:
    if value is None or value == "":
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not isinstance(value, str) or not FIELD.match(value):
        raise ValueError(f"{name} must be a short code (letters, digits . _ : -), not {value!r:.40}")
    return value


class Door:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def page(self, queue, client_context_id=None, alert_code=None, system_id=None, agent=None):
        from . import pager as pg
        record = {"client_context_id": _field("client_context_id", client_context_id)}
        for k, v in (("alert_code", alert_code), ("system_id", system_id), ("agent", agent)):
            if v is not None:
                record[k] = _field(k, v)
        text = pg.page_text(_field("queue", queue, required=True), record)
        try:
            cfg = pg.load_config(self.config_path)
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        if cfg is None:
            return {"status": "failed", "error": "no pager set up in the alert door"}
        return pg.send_page(cfg, text)


def serve(path: str, config_path: str) -> int:
    from .portal import Peer, PortalError
    if os.name != "nt":
        os.umask(0o077)
    door = Door(config_path)
    if os.path.exists(path):
        os.remove(path)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(path)
    os.chmod(path, 0o600)
    server.listen(4)
    print(f"alert door: listening on {path}", flush=True)
    while True:
        conn, _ = server.accept()
        conn.settimeout(30)
        peer = Peer(conn, {"page": door.page}, frozenset({"page"}), name="alert door")
        try:
            peer.serve_forever()
        except PortalError as e:
            print(f"alert door: {e}", file=sys.stderr, flush=True)
        finally:
            peer.close()


class DoorPager:
    """The dispatcher's pager when the alert door is in use: same call as
    dispatcher.pager.Pager, and each attempt recorded the same way."""

    def __init__(self, path: str, timeout: float = 20.0):
        self.path = path
        self.timeout = timeout
        self.audit: Any = None

    def __call__(self, queue: str, record: dict) -> dict:
        from .portal import Peer, PortalError, RemoteError
        rec = record or {}
        fields = {"queue": queue, "client_context_id": rec.get("client_context_id"),
                  "alert_code": rec.get("alert_code"), "system_id": rec.get("system_id"),
                  "agent": rec.get("agent")}
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            s.connect(self.path)
            peer = Peer(s, {}, frozenset(), name="alert door")
            try:
                res = peer.call("page", fields)
            finally:
                peer.close()
        except (OSError, PortalError, RemoteError) as e:
            res = {"status": "failed", "error": f"alert door: {type(e).__name__}: {e}"}
        if self.audit is not None:
            self.audit.append("pager.sent" if res.get("status") == "sent" else "pager.failed",
                              {"queue": queue, "client_context_id": rec.get("client_context_id"),
                               "via": "alert door",
                               **{k: v for k, v in res.items() if k != "status"}})
        return res


def setup(config_path: str) -> int:
    import getpass
    from . import pager as pg
    cfg = {"account_sid": input("Twilio account SID: ").strip(),
           "auth_token": getpass.getpass("Twilio auth token (not shown): ").strip(),
           "from_number": input("Twilio number to send from (+1...): ").strip(),
           "to_number": input("Your mobile number (+1...): ").strip()}
    problems = pg.validate(cfg)
    if problems:
        print(f"not saved: {problems}")
        return 1
    pg.save_config(config_path, cfg)
    res = pg.send_page(cfg, "ListingAssistants: test page from the alert door. Paging works.")
    print(f"saved to {config_path}; test page: {res}")
    return 0 if res["status"] == "sent" else 1


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["serve"] and len(argv) == 3:
        return serve(argv[1], argv[2])
    if argv[:1] == ["setup"] and len(argv) == 2:
        return setup(argv[1])
    print("usage: python -m dispatcher.alert_door serve <socket path> <pager.json>\n"
          "       python -m dispatcher.alert_door setup <pager.json>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
