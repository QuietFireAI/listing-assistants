# The five pillars

Five self-check packages, part of ListingAssistants since 2026-10-20 (owner
decision: one product, the pillars built in, not add-ons). Each watches a
different point in the hub; `dispatcher/pillars.py` binds them.

| Package | Watches | Folded from |
|---|---|---|
| `before_turn/` | the hub re-reads its own recent state before each turn | QuietFireAI/before-turn `0b18252a319a48cb540acf90e9d1508d0b2874ad` |
| `open_mind/` | what the hub reasoned against what it did (drift) | QuietFireAI/open-mind `570e1b8e4c2f141dbcd2cb3b0b9eb1f7fac63ea6` |
| `agent_open_mind/` | an agent result with no reasoning trace is held as tainted | QuietFireAI/agent-open-mind `9b0dc89ce923c3b767e3e4436f6966d8ede99b2a` |
| `pre_response_selfcheck/` | a cold read of outgoing text before it leaves (needs a reviewer model) | QuietFireAI/pre-response-selfcheck `94d6a30cdb41fd8934391114a1979b0071f9e9a0` |
| `sleep_marks/` | the hub's open work, captured at a crew change | QuietFireAI/sleep-marks `8aa298b98b229cbdd76f3caa917298087888f0e8` |

The commits are the ones `requirements.txt` pinned on 2026-10-12, the ones
the suite last passed against as installed packages. The package source was
copied unchanged except one edit: `open_mind/conversation.py` and
`open_mind/conversation_evidence.py` imported their own package by its
installed name (`from open_mind import ...`); they now import it relatively
(`from . import ...`), so the copy here is the one that runs. Each package's
own tests came with it (`tests_listing/test_pillar_*.py`, imports changed
only). agent-open-mind's `adapters/` folder (model adapters for Ollama,
Claude, Gemini, OpenAI) and its 24 tests were not brought in: nothing in the
product uses them.

From 2026-10-20 the pillars are changed and tested here only. Their
repositories are parked: nothing is copied from them or installed from them.

pre-response-selfcheck needs a reviewer model to judge text. Without one
configured, the gate is off and says so on the audit log at boot
(`selfcheck.unarmed`); the other four run on every message.

The sixth pillar, splitvantage (a second opinion from two different models),
was removed by owner decision 2026-10-20.

License: Apache License 2.0 (`LICENSE`, `NOTICE` in this folder, the same
files each pillar repository carried), as for the dispatcher core
(`dispatcher/LICENSE-CORE`).
