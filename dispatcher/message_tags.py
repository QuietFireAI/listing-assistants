"""Message tags for inbound client words (owner decision 2026-10-14).

The agents act on labels such as "angry" or "contradicts stated criteria".
Until 2026-10-14 nothing in the product set them: they had to arrive on the
inbound message from an outside classifier, so in real traffic the tuples
behind them could not fire. The owner chose a phrase-list tagger at intake,
the same mechanism as every other trigger list in the product, and ruled
that any adverse message (angry, upset, negative) goes to the human at once,
whatever else it asks.

Matching is lower-case substring, like the other lists. Phrases common in
neutral messages ("worst case", "still waiting on the lender") are left off
on purpose: an adverse tag holds every outbound touch for that client until
you release it. A phrase not on a
list is not recognized; the lists are PROVISIONAL and listed in
docs/TUNING_MANUAL.md ("Trigger phrase lists"). An explicit label on the
inbound message (an upstream classifier) is honored as well.
"""
from __future__ import annotations

# adverse: the client is angry (tuple 11-14: straight to the human, nothing
# sent to the client)
ANGRY_WORDS = ("ridiculous", "unacceptable", "furious", "angry", "outraged",
               "fed up", "disgusted", "incompetent", "how dare",
               "sue you", "report you", "scam")

# adverse: negative tone short of anger (tuple 11-10: P14 complaint intake)
NEGATIVE_WORDS = ("not happy", "unhappy", "disappointed", "frustrated",
                  "frustrating", "annoyed", "not thrilled", "upset",
                  "not impressed", "poor service", "nobody called",
                  "no one called")

# the client changes what they said they want (Agent 13 tuple 1: ask the
# client to confirm, never rewrite the profile silently)
CRITERIA_CHANGE_WORDS = ("forget the", "changed my mind", "actually i want",
                         "actually we want", "no longer need",
                         "doesn't matter anymore", "matters more",
                         "more important than", "we've decided we want")

# a referral reward is mentioned (Agent 16 tuple 8: compliance first)
REFERRAL_REWARD_WORDS = ("referral reward", "referral fee", "finder's fee",
                         "finders fee", "reward if", "for referring",
                         "kickback", "referral incentive")

_LISTS = {
    "angry": ANGRY_WORDS,
    "negative_tone": NEGATIVE_WORDS,
    "contradicts_stated_criteria": CRITERIA_CHANGE_WORDS,
    "mentions_referral_reward": REFERRAL_REWARD_WORDS,
}

ADVERSE = ("angry", "negative_tone")

# the labels Agent 11 passes on to the agent that owns the reply
FORWARDED = ("contradicts_stated_criteria", "mentions_referral_reward")


def tag_message(text, explicit: dict | None = None) -> dict:
    """{label: matched phrase or "explicit"} for every label that applies.
    An explicit label counts only when it is the boolean True."""
    low = str(text or "").lower()
    out = {}
    for label, words in _LISTS.items():
        hit = next((w for w in words if w in low), None)
        if hit:
            out[label] = hit
        elif explicit and explicit.get(label) is True:
            out[label] = "explicit"
    return out
