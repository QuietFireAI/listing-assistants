"""config_status - one rule for "is this identity config ratified?".

Added 2026-10-11 (audit CFG-2). Agents 07, 08 and 11 had begun loading
config files whose own _status says "PROPOSED DRAFT ... loads fail closed
while status is not RATIFIED", with no status check and with every
exception swallowed. This is the single check they now share.

Rule (fail closed): a status is ratified only when it states RATIFIED
(not "UNRATIFIED", not "not RATIFIED") together with a date in that same
"|"-separated clause, e.g. "RATIFIED 2026-07-17 ..." or
"ALL TEMPLATES RATIFIED Jeff Phillips 2026-07-18". Anything else - draft,
template, missing, ambiguous - is not ratified.
"""
from __future__ import annotations

import json
import os
import re

_RATIFIED_WITH_DATE = re.compile(r"(?<!NOT )(?<!UN)RATIFIED\b[^|]*?\d{4}-\d{2}-\d{2}")


def is_ratified(status) -> bool:
    if not isinstance(status, str):
        return False
    s = status.upper()
    return any(_RATIFIED_WITH_DATE.search(clause) for clause in s.split("|"))


def load_ratified_config(path: str):
    """Returns (data, verdict). verdict is one of:
    'loaded', 'absent', 'unratified', 'invalid: <error>'.
    data is None unless verdict == 'loaded'. Never raises for a bad file -
    the caller declares the verdict on the audit log and keeps its ratified
    code defaults."""
    if not os.path.exists(path):
        return None, "absent"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"invalid: {e!r}"
    if not is_ratified(data.get("_status")):
        return None, "unratified"
    return data, "loaded"
