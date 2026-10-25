"""Blob storage abstraction: a local folder or Azure Blob Storage (and Azurite).

Document status lives in **blob metadata** (there is no database), so both stores support reading and
replacing metadata, and a conditional replace (``if_match``) that two processes can use to claim a blob.
"""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

from .config import Settings

COPY_CHUNK = 1024 * 1024


class PreconditionFailed(Exception):
    """The blob changed since it was read (another process updated it first)."""


@dataclass
class BlobInfo:
    name: str
    size: int
    last_modified: datetime
    etag: str
    content_type: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


def ascii_value(value) -> str:
    """Blob metadata values must be ASCII; replace anything else."""
    return str(value).encode("ascii", "replace").decode("ascii").replace("\n", " ").replace("\r", " ")


class BlobStore(ABC):
    @abstractmethod
    def put_file(self, container: str, name: str, fileobj: BinaryIO, content_type: str | None = None,
                 metadata: dict[str, str] | None = None) -> None: ...

    @abstractmethod
    def iter_bytes(self, container: str, name: str) -> Iterator[bytes]: ...

    @abstractmethod
    def info(self, container: str, name: str) -> BlobInfo | None: ...

    @abstractmethod
    def list(self, container: str, prefix: str = "") -> list[BlobInfo]: ...

    @abstractmethod
    def set_metadata(self, container: str, name: str, metadata: dict[str, str], if_match: str | None = None) -> str:
        """Replace all metadata and return the new ETag. Raises PreconditionFailed if ``if_match`` is stale."""

    @abstractmethod
    def delete(self, container: str, name: str) -> None: ...

    # ---- helpers built on the primitives
    def put_bytes(self, container, name, data: bytes, content_type=None, metadata=None) -> None:
        import io

        self.put_file(container, name, io.BytesIO(data), content_type, metadata)

    def get_bytes(self, container: str, name: str) -> bytes:
        return b"".join(self.iter_bytes(container, name))

    def download_to(self, container: str, name: str, fileobj: BinaryIO) -> int:
        size = 0
        for part in self.iter_bytes(container, name):
            fileobj.write(part)
            size += len(part)
        return size

    def exists(self, container: str, name: str) -> bool:
        return self.info(container, name) is not None

    def put_json(self, container: str, name: str, obj) -> None:
        self.put_bytes(container, name, json.dumps(obj, indent=2, default=str).encode(), "application/json")

    def get_json_or_none(self, container: str, name: str):
        try:
            return json.loads(self.get_bytes(container, name))
        except FileNotFoundError:
            return None


class LocalBlobStore(BlobStore):
    """Containers are folders under ``root``; metadata is a JSON sidecar under ``root/.meta``."""

    _lock = threading.RLock()

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, container: str, name: str) -> Path:
        base = (self.root / container).resolve()
        path = (base / name).resolve()
        if base not in path.parents or container.startswith("."):
            raise ValueError(f"Invalid blob name: {name}")
        return path

    def _meta_path(self, container: str, name: str) -> Path:
        self._path(container, name)  # validates the name
        return self.root / ".meta" / container / f"{name}.json"

    @contextmanager
    def _locked(self):
        """Serialise metadata updates across threads and (on Linux/macOS) processes."""
        with self._lock:
            lock_file = self.root / ".lock"
            with lock_file.open("a") as fh:
                try:
                    import fcntl

                    fcntl.flock(fh, fcntl.LOCK_EX)
                except ImportError:  # Windows: thread lock only
                    pass
                yield

    def _read_meta(self, container, name) -> dict:
        path = self._meta_path(container, name)
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            return {"metadata": {}, "content_type": "", "etag": ""}

    def _write_meta(self, container, name, record: dict) -> str:
        record["etag"] = uuid.uuid4().hex
        path = self._meta_path(container, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(record))
        tmp.replace(path)
        return record["etag"]

    def put_file(self, container, name, fileobj, content_type=None, metadata=None):
        path = self._path(container, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Unique temp name: two writers of the same blob must not share it.
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        with tmp.open("wb") as out:
            shutil.copyfileobj(fileobj, out, COPY_CHUNK)
        with self._locked():
            tmp.replace(path)
            self._write_meta(container, name, {"metadata": {k: ascii_value(v) for k, v in (metadata or {}).items()},
                                               "content_type": content_type or ""})

    def iter_bytes(self, container, name):
        path = self._path(container, name)
        if not path.is_file():
            raise FileNotFoundError(f"{container}/{name}")

        def gen():
            with path.open("rb") as fh:
                while part := fh.read(COPY_CHUNK):
                    yield part

        return gen()

    def info(self, container, name):
        path = self._path(container, name)
        if not path.is_file():
            return None
        stat = path.stat()
        meta = self._read_meta(container, name)
        return BlobInfo(name=name, size=stat.st_size,
                        last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        etag=meta.get("etag") or f"{stat.st_mtime_ns}", content_type=meta.get("content_type", ""),
                        metadata=dict(meta.get("metadata", {})))

    def list(self, container, prefix=""):
        base = self.root / container
        if not base.is_dir():
            return []
        names = sorted(p.relative_to(base).as_posix() for p in base.rglob("*")
                       if p.is_file() and not p.name.endswith(".tmp"))
        return [i for n in names if n.startswith(prefix) and (i := self.info(container, n))]

    def set_metadata(self, container, name, metadata, if_match=None):
        with self._locked():
            if not self._path(container, name).is_file():
                raise FileNotFoundError(f"{container}/{name}")
            record = self._read_meta(container, name)
            current = record.get("etag") or f"{self._path(container, name).stat().st_mtime_ns}"
            if if_match is not None and if_match != current:
                raise PreconditionFailed(f"{container}/{name}")
            record["metadata"] = {k: ascii_value(v) for k, v in metadata.items()}
            return self._write_meta(container, name, record)

    def delete(self, container, name):
        with self._locked():
            self._path(container, name).unlink(missing_ok=True)
            self._meta_path(container, name).unlink(missing_ok=True)

    def clear(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        self.root.mkdir(parents=True, exist_ok=True)


class AzureBlobStore(BlobStore):
    def __init__(self, settings: Settings):
        from azure.storage.blob import BlobServiceClient

        if settings.storage_connection_string:
            self.client = BlobServiceClient.from_connection_string(settings.storage_connection_string)
        elif settings.storage_account_url:
            from .azure_auth import get_credential

            self.client = BlobServiceClient(settings.storage_account_url, credential=get_credential())
        else:
            raise RuntimeError("Set AZURE_STORAGE_ACCOUNT_URL (or AZURE_STORAGE_CONNECTION_STRING for Azurite)")
        self._ensured: set[str] = set()

    def _container(self, container: str):
        client = self.client.get_container_client(container)
        if container not in self._ensured:
            from azure.core.exceptions import ResourceExistsError

            try:
                client.create_container()
            except ResourceExistsError:
                pass
            self._ensured.add(container)
        return client

    @staticmethod
    def _to_info(name, props) -> BlobInfo:
        content_settings = getattr(props, "content_settings", None)
        return BlobInfo(name=name, size=props.size or 0, last_modified=props.last_modified,
                        etag=(props.etag or "").strip('"'),
                        content_type=(content_settings.content_type if content_settings else "") or "",
                        metadata=dict(props.metadata or {}))

    def put_file(self, container, name, fileobj, content_type=None, metadata=None):
        from azure.storage.blob import ContentSettings

        settings = ContentSettings(content_type=content_type) if content_type else None
        self._container(container).upload_blob(
            name, fileobj, overwrite=True, content_settings=settings, max_concurrency=1,
            metadata={k: ascii_value(v) for k, v in (metadata or {}).items()},
        )

    def iter_bytes(self, container, name):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._container(container).download_blob(name, max_concurrency=1).chunks()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(f"{container}/{name}") from exc

    def info(self, container, name):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            props = self._container(container).get_blob_client(name).get_blob_properties()
        except ResourceNotFoundError:
            return None
        return self._to_info(name, props)

    def list(self, container, prefix=""):
        blobs = self._container(container).list_blobs(name_starts_with=prefix or None, include=["metadata"])
        return sorted((self._to_info(b.name, b) for b in blobs), key=lambda i: i.name)

    def set_metadata(self, container, name, metadata, if_match=None):
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceModifiedError, ResourceNotFoundError

        blob = self._container(container).get_blob_client(name)
        kwargs = {"etag": f'"{if_match}"', "match_condition": MatchConditions.IfNotModified} if if_match else {}
        try:
            result = blob.set_blob_metadata({k: ascii_value(v) for k, v in metadata.items()}, **kwargs)
        except ResourceModifiedError as exc:
            raise PreconditionFailed(f"{container}/{name}") from exc
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(f"{container}/{name}") from exc
        return str(result.get("etag", "")).strip('"')

    def delete(self, container, name):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self._container(container).delete_blob(name, delete_snapshots="include")
        except ResourceNotFoundError:
            pass
