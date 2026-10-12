"""Owner decision 2026-10-12: Agent 11 sends nothing to a client without
consent on record at Agent 14. Tests that exercise a client send record that
consent first, the way it happens in real traffic (01 records a lead's
consent at capture; for any other client the broker signs a consent_record)."""
from dispatcher.core import Envelope


def give_consent(hub, *ctxs, channels=("email",)):
    if "14" not in getattr(hub, "handlers", {}):
        from dispatcher.listing_spokes import Spoke14CRMPipeline
        Spoke14CRMPipeline(hub)
    for ctx in ctxs:
        res = hub.send(Envelope(from_agent="01", to_agent="14", intent="interaction.log",
                                client_context_id=ctx,
                                payload={"kind": "consent_on_record",
                                         "consent": {c: "yes" for c in channels}},
                                provenance={"source": "spoke-01", "captured_at": "runtime"}))
        assert res["status"] == "ack", res
