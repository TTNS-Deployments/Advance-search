import pytest

from advancesearch.config import reset_settings_cache

BACKEND_VARS = ("ADVSEARCH_MODE", "STORAGE_BACKEND", "SEARCH_BACKEND", "EMBEDDING_BACKEND", "INGEST_WORKER",
                "EMBEDDING_DIMENSIONS", "MAX_UPLOAD_MB")


@pytest.fixture(autouse=True)
def local_mode(tmp_path, monkeypatch):
    """Every test runs in local mode against a fresh, empty data folder, processing documents inline."""
    for name in BACKEND_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INGEST_WORKER", "inline")
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "256")  # smaller vectors keep the tests fast
    reset_settings_cache()
    yield
    reset_settings_cache()


@pytest.fixture
def service():
    from advancesearch.ingest import get_document_service

    svc = get_document_service()
    svc.index.ensure()
    return svc
