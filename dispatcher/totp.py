"""totp - the six-digit code from an authenticator app (RFC 6238).

Owner decision 2026-10-26: signing needs a second factor; in V1 that is the
code from an authenticator app (Google Authenticator, Authy, 1Password and
the like), typed on the signer's own page. It works with no internet: the
app and the signer each compute the code from a shared secret and the time.

HMAC-SHA1, 30-second steps, 6 digits: what every authenticator app uses by
default. A code is accepted for the current step and one step either side
(clock drift), and each step is accepted once: a code seen once is refused
the second time, so a code read over your shoulder is useless.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse
from typing import Optional

STEP = 30
DIGITS = 6


def new_secret() -> str:
    """A random 160-bit secret, base32 as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret_b32: str) -> bytes:
    s = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret_b32: str, counter: int) -> str:
    mac = hmac.new(_key(secret_b32), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(n).zfill(DIGITS)


def counter_now(t: Optional[float] = None) -> int:
    return int((time.time() if t is None else t) // STEP)


def verify(secret_b32: str, code: str, last_counter: int, t: Optional[float] = None,
           window: int = 1) -> Optional[int]:
    """The step the code belongs to when it is right and newer than
    last_counter (each step is used once), else None."""
    code = (code or "").strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    now = counter_now(t)
    for c in range(now - window, now + window + 1):
        if c > last_counter and hmac.compare_digest(code_at(secret_b32, c), code):
            return c
    return None


def otpauth_uri(secret_b32: str, account: str, issuer: str = "ListingAssistants") -> str:
    """What an authenticator app scans or accepts by hand."""
    label = urllib.parse.quote(f"{issuer}:{account}")
    q = urllib.parse.urlencode({"secret": secret_b32, "issuer": issuer,
                                "algorithm": "SHA1", "digits": DIGITS, "period": STEP})
    return f"otpauth://totp/{label}?{q}"
