"""The ingestion worker: one background thread per app process, one document at a time.

* ``INGEST_WORKER=thread`` (default): a daemon thread processes the queue. On start-up it scans the documents
  container and queues every blob that is not indexed (this recovers files left in ``processing`` by a restart
  and picks up files uploaded straight to storage). Every ``SYNC_INTERVAL_SECONDS`` it scans again for new
  files only.
* ``INGEST_WORKER=inline``: documents are processed in the calling thread (tests, CLI).
* ``INGEST_WORKER=off``: nothing is processed in this process.
"""

from __future__ import annotations

import logging
import queue
import threading
import time

log = logging.getLogger(__name__)

_worker = None
_worker_lock = threading.Lock()


class Worker:
    def __init__(self, service_factory, mode: str = "thread", sync_interval: int = 300):
        self.service_factory = service_factory
        self.mode = mode
        self.sync_interval = max(10, sync_interval)
        self.queue: queue.Queue[str | None] = queue.Queue()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.current: str | None = None

    # ------------------------------------------------------------------ API
    def start(self) -> None:
        if self.mode != "thread" or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="advancesearch-ingest", daemon=True)
        self._thread.start()
        log.info("Ingestion worker started")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self.queue.put(None)
        if self._thread:
            self._thread.join(timeout)

    def enqueue(self, name: str) -> None:
        if self.mode == "inline":
            self._process(name)
            return
        with self._lock:
            if name in self._pending:
                return
            self._pending.add(name)
        self.queue.put(name)

    def sync(self, include_finished: bool = True) -> list[str]:
        """Queue documents that need processing; returns their names."""
        names = self.service_factory().pending(include_finished=include_finished)
        for name in names:
            self.enqueue(name)
        return names

    @property
    def backlog(self) -> int:
        with self._lock:
            return len(self._pending)

    # ------------------------------------------------------------------ internals
    def _process(self, name: str) -> None:
        self.current = name
        try:
            self.service_factory().process(name)
        except Exception:  # noqa: BLE001 - the worker must keep running
            log.exception("Worker failed on %s", name)
        finally:
            self.current = None

    def _run(self) -> None:
        try:
            self.sync(include_finished=True)
        except Exception:  # noqa: BLE001 - storage may not be reachable yet; the periodic scan retries
            log.warning("Start-up scan failed", exc_info=True)
        next_scan = time.monotonic() + self.sync_interval
        while not self._stop.is_set():
            timeout = max(0.5, next_scan - time.monotonic())
            try:
                name = self.queue.get(timeout=timeout)
            except queue.Empty:
                name = None
            if name:
                with self._lock:
                    self._pending.discard(name)
                self._process(name)
            if time.monotonic() >= next_scan:
                try:
                    self.sync(include_finished=False)
                except Exception:  # noqa: BLE001
                    log.warning("Periodic scan failed", exc_info=True)
                next_scan = time.monotonic() + self.sync_interval


def get_worker() -> Worker:
    global _worker
    with _worker_lock:
        if _worker is None:
            from .config import get_settings
            from .ingest import get_document_service

            s = get_settings()
            _worker = Worker(get_document_service, s.worker_mode, s.sync_interval_seconds)
        return _worker


def reset() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop(timeout=1.0)
        _worker = None
