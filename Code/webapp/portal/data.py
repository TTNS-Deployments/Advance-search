"""Thin access layer from the web app to the ``advancesearch`` package (one place to patch in tests)."""

from __future__ import annotations

import logging
import time

from advancesearch import factory
from advancesearch.config import get_settings
from advancesearch.ingest import INDEXED, get_document_service
from advancesearch.search import search
from advancesearch.worker import get_worker

log = logging.getLogger(__name__)

_status_cache: dict = {}
STATUS_SECONDS = 60


def service():
    return get_document_service()


def worker():
    return get_worker()


def settings_store():
    return factory.get_settings_store()


def run_search(query: str):
    return search(query)


def document(doc_id: str, name: str):
    return service().find(doc_id, name)


def image_store():
    return factory.get_image_store()


def indexed_count() -> int:
    return sum(1 for d in service().list() if d.status == INDEXED)


def index_status():
    """Index status, cached for a minute (in Azure it costs a service call)."""
    cached = _status_cache.get("status")
    if cached and time.monotonic() - cached[0] < STATUS_SECONDS:
        return cached[1]
    try:
        status = factory.get_index().ensure()
    except Exception:  # noqa: BLE001
        log.warning("Could not read the index status", exc_info=True)
        return None
    _status_cache["status"] = (time.monotonic(), status)
    return status


def reset_index_status() -> None:
    _status_cache.clear()


def index_warning() -> str:
    status = index_status()
    if status is None:
        return "The search index could not be reached. Searches and indexing will fail until it is available."
    return status.warning


def system_info() -> dict:
    s = get_settings()
    try:
        status = factory.get_index().status()
    except Exception:  # noqa: BLE001
        status = None
    return {
        "environment": s.environment_name, "mode": s.mode, "storage": s.storage_backend, "search": s.search_backend,
        "embeddings": s.embedding_backend, "index_name": s.search_index_name,
        "embedding_deployment": s.embedding_deployment if s.embedding_backend == "azure" else "mock (local)",
        "dimensions": s.embedding_dimensions, "index_dimensions": status.dimensions if status else None,
        "passages": status.chunks if status else None, "max_upload_mb": s.max_upload_mb,
    }
