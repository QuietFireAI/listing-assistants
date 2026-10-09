"""dispatcher.concurrent_dispatcher - Multi-tenant concurrent actor dispatcher.

Architecture:
- High-throughput concurrency across distinct client contexts (properties/deals).
- Strict FIFO actor sequencing per client context (partition key: client_context_id):
  prevents state tearing, out-of-order sequence counter attribution, and race conditions
  on individual client drawers while allowing massive multi-tenant parallel throughput.
- Dual interface:
  1. Synchronous / ThreadPool Future API (dispatch, send).
  2. Asyncio coroutine API (async_send) for event-loop native integration (FastAPI / ASGI).
- Thread-safe actor coordination via worker pool and partition scheduling locks.
"""
from __future__ import annotations
import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from collections import deque
import threading
from typing import Any, Callable, Dict, Optional, Set, Tuple

from .core import Envelope
from .hub import Hub


class ConcurrentHubDispatcher:
    """Manages concurrent execution of envelopes through the Hub.

    Key Invariant:
    Envelopes for the SAME `client_context_id` are executed strictly sequentially (FIFO)
    to protect audit chain monotonicity and client state integrity.
    Envelopes for DIFFERENT `client_context_id`s execute concurrently across worker threads.
    """

    def __init__(self, hub: Hub, max_workers: int = 8):
        self.hub = hub
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="HubWorker")
        self._lock = threading.Lock()
        # Per-client pending queues: client_context_id -> deque of (Envelope, Future)
        self._client_queues: Dict[str, deque[Tuple[Envelope, Future]]] = {}
        # Set of client_context_ids currently being processed by a worker thread
        self._active_clients: Set[str] = set()
        self._shutdown = False
        self._processed_count = 0

    @property
    def processed_count(self) -> int:
        with self._lock:
            return self._processed_count

    def dispatch(self, env: Envelope) -> Future:
        """Submit an envelope for processing. Returns a concurrent.futures.Future.

        Processing is scheduled immediately if no other worker is currently executing
        an envelope for env.client_context_id. Otherwise, it is enqueued in that
        client's FIFO queue.
        """
        with self._lock:
            if self._shutdown:
                raise RuntimeError("ConcurrentHubDispatcher is shut down")

            fut: Future = Future()
            client_id = env.client_context_id
            if client_id not in self._client_queues:
                self._client_queues[client_id] = deque()

            self._client_queues[client_id].append((env, fut))

            if client_id not in self._active_clients:
                self._active_clients.add(client_id)
                self._executor.submit(self._worker_loop, client_id)

            return fut

    def send(self, env: Envelope, timeout: Optional[float] = None) -> dict:
        """Synchronously dispatch an envelope and wait for result."""
        fut = self.dispatch(env)
        return fut.result(timeout=timeout)

    async def async_send(self, env: Envelope) -> dict:
        """Asynchronously dispatch an envelope and await result on asyncio event loop."""
        fut = self.dispatch(env)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fut.result)

    def _worker_loop(self, client_id: str) -> None:
        """Worker task processing envelopes for a single client in strict FIFO order."""
        while True:
            item: Optional[Tuple[Envelope, Future]] = None
            with self._lock:
                queue = self._client_queues.get(client_id)
                if queue and len(queue) > 0:
                    item = queue.popleft()
                else:
                    # No more items for this client right now; release active lease
                    self._active_clients.discard(client_id)
                    if queue is not None and len(queue) == 0:
                        del self._client_queues[client_id]
                    return

            env, fut = item
            try:
                result = self.hub.send(env)
                with self._lock:
                    self._processed_count += 1
                fut.set_result(result)
            except Exception as exc:
                fut.set_exception(exc)

    def stats(self) -> dict:
        """Return runtime statistics for monitoring and telemetry."""
        with self._lock:
            return {
                "max_workers": self.max_workers,
                "active_clients": len(self._active_clients),
                "queued_clients": len(self._client_queues),
                "total_queued_envelopes": sum(len(q) for q in self._client_queues.values()),
                "processed_count": self._processed_count,
                "is_shutdown": self._shutdown,
            }

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the concurrent dispatcher."""
        with self._lock:
            self._shutdown = True
        self._executor.shutdown(wait=wait)
