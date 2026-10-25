"""Runtime settings, read from environment variables.

``ADVSEARCH_MODE`` sets the default for every backend:

* ``local`` (default): a folder for storage, a SQLite index with local hybrid search, mock embeddings.
* ``azure``: Blob Storage, Azure AI Search, Azure OpenAI embeddings.

Each backend can be overridden on its own (``STORAGE_BACKEND``, ``SEARCH_BACKEND``, ``EMBEDDING_BACKEND``),
for example run locally but call the real Azure OpenAI with ``EMBEDDING_BACKEND=azure``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default).strip()
    # An unresolved App Service Key Vault reference arrives as the literal reference string.
    return "" if value.startswith("@Microsoft.KeyVault(") else value


def _env_int(name: str, default: int) -> int:
    value = _env(name) or str(default)
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {value!r}") from None


MODES = ("local", "azure")


def find_repo_dir(name: str) -> Path | None:
    """Walk up from this package looking for a sibling folder (``Config``, ``Data``).

    Works both in the repo (Code/core/advancesearch -> repo root) and in a deployed
    app package where the folder is copied next to the package.
    """
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        candidate = parent / name
        if candidate.is_dir():
            return candidate
    return None


@dataclass(frozen=True)
class Settings:
    mode: str = "local"
    environment_name: str = "local"

    # Storage
    storage_backend: str = "local"
    local_data_dir: Path = field(default_factory=lambda: Path(".localdata"))
    storage_connection_string: str = ""
    storage_account_url: str = ""
    container_documents: str = "documents"
    container_config: str = "config"

    # Search index
    search_backend: str = "local"
    search_endpoint: str = ""
    search_api_key: str = ""
    search_index_name: str = "advance-search"

    # Embeddings
    embedding_backend: str = "mock"
    openai_endpoint: str = ""
    openai_key: str = ""
    openai_api_version: str = "2024-10-21"
    embedding_deployment: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Ingestion
    max_upload_mb: int = 20
    worker_mode: str = "thread"        # thread | inline | off
    sync_interval_seconds: int = 300
    processing_stale_minutes: int = 15

    # Managed identity (user-assigned); empty = system-assigned / developer login
    azure_client_id: str = ""

    config_dir: Path | None = None
    data_dir: Path | None = None

    @property
    def is_local(self) -> bool:
        return self.mode == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    mode = _env("ADVSEARCH_MODE", "local").lower()
    if mode not in MODES:
        raise ValueError(f"Unknown ADVSEARCH_MODE {mode!r} (local or azure)")
    azure = mode == "azure"

    config_dir = _env("ADVSEARCH_CONFIG_DIR")
    data_dir = _env("ADVSEARCH_SAMPLE_DATA_DIR")
    worker_mode = _env("INGEST_WORKER", "thread").lower()
    if worker_mode not in {"thread", "inline", "off"}:
        raise ValueError(f"Unknown INGEST_WORKER {worker_mode!r} (thread, inline or off)")

    return Settings(
        mode=mode,
        environment_name=_env("ENVIRONMENT_NAME", "local" if not azure else "azure"),
        storage_backend=_env("STORAGE_BACKEND", "azure" if azure else "local").lower(),
        local_data_dir=Path(_env("LOCAL_DATA_DIR", str(_default_local_data_dir()))),
        storage_connection_string=_env("AZURE_STORAGE_CONNECTION_STRING"),
        storage_account_url=_env("AZURE_STORAGE_ACCOUNT_URL"),
        container_documents=_env("CONTAINER_DOCUMENTS", "documents"),
        container_config=_env("CONTAINER_CONFIG", "config"),
        search_backend=_env("SEARCH_BACKEND", "azure" if azure else "local").lower(),
        search_endpoint=_env("SEARCH_ENDPOINT").rstrip("/"),
        search_api_key=_env("SEARCH_API_KEY"),
        search_index_name=_env("SEARCH_INDEX_NAME", "advance-search"),
        embedding_backend=_env("EMBEDDING_BACKEND", "azure" if azure else "mock").lower(),
        openai_endpoint=_env("AZURE_OPENAI_ENDPOINT").rstrip("/"),
        openai_key=_env("AZURE_OPENAI_KEY"),
        openai_api_version=_env("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        embedding_deployment=_env("EMBEDDING_DEPLOYMENT", "text-embedding-3-small"),
        embedding_dimensions=_env_int("EMBEDDING_DIMENSIONS", 1536),
        max_upload_mb=_env_int("MAX_UPLOAD_MB", 20),
        worker_mode=worker_mode,
        sync_interval_seconds=_env_int("SYNC_INTERVAL_SECONDS", 300),
        processing_stale_minutes=_env_int("PROCESSING_STALE_MINUTES", 15),
        azure_client_id=_env("AZURE_CLIENT_ID"),
        config_dir=Path(config_dir) if config_dir else find_repo_dir("Config"),
        data_dir=Path(data_dir) if data_dir else find_repo_dir("Data"),
    )


def _default_local_data_dir() -> Path:
    root = find_repo_dir("Code")
    # repo/Code exists -> keep local data at repo/.localdata
    return (root.parent / ".localdata") if root else Path(".localdata")


def reset_settings_cache() -> None:
    """Used by tests after changing environment variables."""
    get_settings.cache_clear()
    from . import factory

    factory.reset()
