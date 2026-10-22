# Where the dispatcher core came from

Sixteen files in this folder started in the separate dispatcher-agents
project (https://github.com/QuietFireAI/dispatcher-agents):

    __init__.py  absolute_signal.py  after_action.py  analysis.py
    attestation.py  core.py  hub.py  kpi.py  loader.py  notifier.py
    pillars.py  priority.py  runs.py  signatures.py  signer_registry.py
    territory.py

Until 2026-10-20 they were copied in from that project and CI checked that
the copies matched a pinned dispatcher-agents commit byte for byte
(tools/sync_core.py and CORE_PIN.json).

Owner decision 2026-10-20: ListingAssistants is one product. The core was
folded in from dispatcher-agents commit
8920a38789871acd1ec0594dc2bd4707a322bc01 (branch hub-fail-closed-2026-10-14,
copied 2026-10-15; that branch was never merged into dispatcher-agents
main). From that day the sixteen files are changed and tested here, in this
repository's suite, and nowhere else. dispatcher-agents is parked: nothing
is copied from it or checked against it.

The license notice for these files is LICENSE-CORE in this folder; the fold
did not change it.
