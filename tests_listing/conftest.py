"""Pins the agents' clock for the suite (owner decision D-A4, 2026-10-28).

Agents 03 and 11 use this computer's clock when a message carries no time of
day. Without a pin, a run at night would hold client messages for quiet hours
and the suite's results would depend on when it ran. Noon is inside every
contact window; a test about the time of day sets LISTING_CLOCK_NOW itself
(monkeypatch.setenv) or replaces the agent's NOW.
"""
import os

os.environ.setdefault("LISTING_CLOCK_NOW", "2026-10-15T12:00:00")
