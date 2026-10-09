import asyncio
import os
import tempfile
import time

from dispatcher.core import Envelope, Routes, AuditLog
from dispatcher.hub import Hub
from dispatcher.concurrent_dispatcher import ConcurrentHubDispatcher


def make_test_hub(tmpdir):
    audit_path = os.path.join(tmpdir, "audit.jsonl")
    audit = AuditLog(audit_path)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    routes = Routes(os.path.join(root, "identity", "routes.json"))
    hub = Hub(routes, audit)
    processed = []
    def handler(env):
        time.sleep(0.002)  # small simulated processing latency
        processed.append(env)
    hub.register("02", handler)
    return hub, processed


def test_concurrent_dispatcher_multi_client():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub, processed = make_test_hub(tmpdir)
        dispatcher = ConcurrentHubDispatcher(hub, max_workers=8)

        num_clients = 20
        envelopes_per_client = 5
        futures = []

        for c in range(num_clients):
            client_id = f"client_{c:03d}"
            for seq in range(envelopes_per_client):
                env = Envelope(
                    from_agent="01",
                    to_agent="02",
                    intent="lead.captured",
                    client_context_id=client_id,
                    payload={"seq": seq, "val": f"lead_{c}_{seq}"},
                    provenance={"source": "01"},
                    confidence="source_verified"
                )
                futures.append(dispatcher.dispatch(env))

        # Collect all results
        results = [fut.result(timeout=10.0) for fut in futures]

        assert len(results) == num_clients * envelopes_per_client
        assert all(r["status"] == "ack" for r in results)

        # Invariant check: for EACH client, sequences processed must be strictly ascending (FIFO)
        client_sequences = {}
        for env in processed:
            cid = env.client_context_id
            client_sequences.setdefault(cid, []).append(env.payload["seq"])

        for cid, seqs in client_sequences.items():
            assert seqs == list(range(envelopes_per_client)), (
                f"Client {cid} out of order: expected {list(range(envelopes_per_client))}, got {seqs}"
            )

        stats = dispatcher.stats()
        assert stats["processed_count"] == num_clients * envelopes_per_client
        dispatcher.shutdown(wait=True)


def test_concurrent_dispatcher_async_send():
    with tempfile.TemporaryDirectory() as tmpdir:
        hub, _ = make_test_hub(tmpdir)
        dispatcher = ConcurrentHubDispatcher(hub, max_workers=4)

        async def run_async_test():
            env = Envelope(
                from_agent="01",
                to_agent="02",
                intent="lead.captured",
                client_context_id="async_client",
                payload={"action": "async_call"},
                provenance={"source": "01"},
                confidence="source_verified"
            )
            res = await dispatcher.async_send(env)
            return res

        result = asyncio.run(run_async_test())
        assert result["status"] == "ack"
        dispatcher.shutdown(wait=True)
