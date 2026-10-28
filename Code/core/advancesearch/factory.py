"""Builds the configured implementation of each dependency (cached per process)."""

from __future__ import annotations

from functools import lru_cache

from .config import get_settings


def _unknown(kind: str, value: str):
    return ValueError(f"Unknown {kind} backend '{value}'")


@lru_cache(maxsize=1)
def get_blob_store():
    from . import storage

    s = get_settings()
    if s.storage_backend == "local":
        return storage.LocalBlobStore(s.local_data_dir / "storage")
    if s.storage_backend == "azure":
        return storage.AzureBlobStore(s)
    raise _unknown("storage", s.storage_backend)


@lru_cache(maxsize=1)
def get_index():
    from . import index

    s = get_settings()
    if s.search_backend == "local":
        return index.LocalIndex(s.local_data_dir / "index.sqlite3", s.embedding_dimensions)
    if s.search_backend == "azure":
        return index.AzureSearchIndex(s)
    raise _unknown("search", s.search_backend)


@lru_cache(maxsize=1)
def get_embedder():
    from . import embeddings

    s = get_settings()
    if s.embedding_backend == "mock":
        return embeddings.MockEmbeddings(s.embedding_dimensions)
    if s.embedding_backend == "azure":
        return embeddings.AzureOpenAIEmbeddings(s)
    raise _unknown("embedding", s.embedding_backend)


@lru_cache(maxsize=1)
def get_image_store():
    from .images import ImageStore

    return ImageStore(get_blob_store(), get_settings().container_images)


@lru_cache(maxsize=1)
def get_settings_store():
    from .settings_store import SettingsStore

    return SettingsStore(get_blob_store(), get_settings())


def reset() -> None:
    for fn in (get_blob_store, get_index, get_embedder, get_image_store, get_settings_store):
        fn.cache_clear()
    from . import settings_store, worker

    settings_store.load_defaults.cache_clear()
    worker.reset()
