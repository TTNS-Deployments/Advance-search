"""The Azure Blob Storage code path (AzureBlobStore) against the Azurite emulator.

Skipped unless Azurite listens on 127.0.0.1:10000, for example:
    docker run -d --rm -p 10000:10000 mcr.microsoft.com/azure-storage/azurite:3.33.0 azurite-blob --blobHost 0.0.0.0 --skipApiVersionCheck --loose
"""
from __future__ import annotations

import socket
import uuid

import pytest
from live_server import SAMPLES

CONNECTION = ("DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDX"
              "J1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;")


def azurite_running() -> bool:
    try:
        socket.create_connection(("127.0.0.1", 10000), timeout=1).close()
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not azurite_running(), reason="Azurite is not running on 127.0.0.1:10000")


@pytest.fixture
def service(tmp_path, monkeypatch):
    from advancesearch.config import reset_settings_cache
    from advancesearch.ingest import get_document_service

    suffix = uuid.uuid4().hex[:8]
    for k, v in {"ADVSEARCH_MODE": "local", "STORAGE_BACKEND": "azure", "AZURE_STORAGE_CONNECTION_STRING": CONNECTION,
                 "LOCAL_DATA_DIR": str(tmp_path), "INGEST_WORKER": "inline", "CONTAINER_DOCUMENTS": f"docs{suffix}",
                 "CONTAINER_CONFIG": f"cfg{suffix}", "EMBEDDING_DIMENSIONS": "512"}.items():
        monkeypatch.setenv(k, v)
    reset_settings_cache()
    svc = get_document_service()
    yield svc
    from azure.core.exceptions import ResourceNotFoundError

    for c in (f"docs{suffix}", f"cfg{suffix}"):
        try:
            svc.blobs.client.delete_container(c)
        except ResourceNotFoundError:
            pass
    reset_settings_cache()


def test_AZ01_ingest_search_and_status_metadata(service):
    from advancesearch.search import search

    for name in ("Leave-Policy-2026.pdf", "Procurement-Approval-Matrix.xlsx", "Scanned-Delivery-Note.pdf"):
        path = SAMPLES / name
        with path.open("rb") as fh:
            service.upload(name, fh, path.stat().st_size, "Admin")
        service.process(name)
    statuses = {d.name: (d.status, d.chunks) for d in service.list()}
    assert statuses["Leave-Policy-2026.pdf"] == ("indexed", 3)
    assert statuses["Scanned-Delivery-Note.pdf"] == ("no_text", 0)
    assert search("how many days off do I get").results[0].file_name == "Leave-Policy-2026.pdf"
    assert service.blobs.get_bytes(service.container, "Leave-Policy-2026.pdf") == (SAMPLES / "Leave-Policy-2026.pdf").read_bytes()


def test_AZ02_conditional_claim(service):
    from advancesearch.storage import PreconditionFailed

    service.blobs.put_bytes(service.container, "a.pdf", b"%PDF-1.4 x", metadata={"status": "queued"})
    stale = service.blobs.info(service.container, "a.pdf").etag
    assert service.claim("a.pdf")
    with pytest.raises(PreconditionFailed):
        service.blobs.set_metadata(service.container, "a.pdf", {"status": "processing"}, if_match=stale)
    assert not service.claim("a.pdf")


def test_AZ03_settings_overrides_and_delete(service):
    from advancesearch import factory

    factory.get_settings_store().save({"top_n": 4})
    factory.reset()
    assert factory.get_settings_store().effective()["top_n"] == 4
    path = SAMPLES / "Leave-Policy-2026.pdf"
    with path.open("rb") as fh:
        service.upload(path.name, fh, path.stat().st_size, "Admin")
    service.process(path.name)
    assert service.delete(path.name) == 3
    assert service.get(path.name) is None
