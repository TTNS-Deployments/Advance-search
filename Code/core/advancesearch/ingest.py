"""Document ingestion: upload validation, the status state machine and the extract -> chunk -> embed -> index step.

Status lives in blob metadata on the document itself (no database)::

    queued -> processing -> indexed
                         -> no_text   (no extractable text, for example a scanned PDF)
                         -> failed    (with an error message)

A process claims a document by replacing its metadata with ``status=processing`` conditionally on the ETag it
read, so two processes can never ingest the same file at the same time.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import socket
import tempfile
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from .chunk import ChunkOptions
from .extract import CONTENT_TYPES, FILE_TYPES, ExtractionError, extract_passages, file_type_for
from .storage import PreconditionFailed

log = logging.getLogger(__name__)

QUEUED, PROCESSING, INDEXED, FAILED, NO_TEXT = "queued", "processing", "indexed", "failed", "no_text"
STATUSES = (QUEUED, PROCESSING, INDEXED, FAILED, NO_TEXT)
NO_TEXT_MESSAGE = "No searchable text found. This file may be a scan."
MAGIC = {"pdf": b"%PDF-", "docx": b"PK\x03\x04", "xlsx": b"PK\x03\x04"}
ZIP_MARKERS = {"docx": "word/document.xml", "xlsx": "xl/workbook.xml"}
MAX_NAME_LENGTH = 120
HASH_CHUNK = 1024 * 1024

# Identifies this process in claims: host (App Service instance) + process id + start-up token.
INSTANCE = os.environ.get("WEBSITE_INSTANCE_ID", "")[:12] or socket.gethostname()
WORKER_ID = f"{INSTANCE}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class UploadError(ValueError):
    """An upload was refused; the message is shown to the admin."""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def doc_id_for(name: str) -> str:
    """Stable document id (index key safe) derived from the blob name."""
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:32]


def sanitize_filename(name: str) -> str:
    """ASCII file name without folders or unsafe characters; keeps the extension."""
    name = PurePosixPath(str(name).replace("\\", "/")).name
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    stem = re.sub(r"[^A-Za-z0-9 ._()-]+", "_", stem)
    stem = re.sub(r"[ _]{2,}", "_", stem).strip(" ._-") or "document"
    ext = re.sub(r"[^A-Za-z0-9]", "", ext).lower()
    stem = stem[: MAX_NAME_LENGTH - len(ext) - 1]
    return f"{stem}.{ext}" if ext else stem


def _short_error(exc: BaseException | str) -> str:
    text = str(exc) if isinstance(exc, str) else (str(exc) or exc.__class__.__name__)
    return " ".join(text.split())[:250]


def check_content(file_type: str, fileobj: BinaryIO) -> None:
    """Magic bytes, and for Office files the zip entry that identifies the format."""
    fileobj.seek(0)
    head = fileobj.read(8)
    fileobj.seek(0)
    if not head.startswith(MAGIC[file_type]):
        raise UploadError(f"The file content is not a valid .{file_type} file.")
    if file_type in ZIP_MARKERS:
        try:
            with zipfile.ZipFile(fileobj) as zf:
                if ZIP_MARKERS[file_type] not in zf.namelist():
                    raise UploadError(f"The file content is not a valid .{file_type} file.")
        except zipfile.BadZipFile:
            raise UploadError(f"The file content is not a valid .{file_type} file.") from None
        finally:
            fileobj.seek(0)


def validate_upload(name: str, fileobj: BinaryIO, size: int, max_mb: int) -> tuple[str, str]:
    """Return ``(safe_name, file_type)`` or raise UploadError."""
    safe = sanitize_filename(name)
    file_type = file_type_for(safe)
    if not file_type:
        raise UploadError("Only PDF (.pdf), Word (.docx) and Excel (.xlsx) files are supported.")
    if size <= 0:
        raise UploadError("The file is empty.")
    if size > max_mb * 1024 * 1024:
        raise UploadError(f"The file is larger than the {max_mb} MB limit.")
    check_content(file_type, fileobj)
    return safe, file_type


def sha256_of(fileobj: BinaryIO) -> str:
    fileobj.seek(0)
    digest = hashlib.sha256()
    while part := fileobj.read(HASH_CHUNK):
        digest.update(part)
    fileobj.seek(0)
    return digest.hexdigest()


@dataclass
class DocumentInfo:
    name: str
    doc_id: str
    file_type: str
    size: int
    status: str
    error: str
    chunks: int
    uploaded_at: datetime | None
    uploaded_by: str
    indexed_at: datetime | None
    content_hash: str

    @property
    def in_progress(self) -> bool:
        return self.status in (QUEUED, PROCESSING)


@dataclass
class UploadResult:
    name: str
    doc_id: str
    replaced: bool


class DocumentService:
    """Every document operation used by the web app, the worker and the CLI."""

    def __init__(self, blobs, index, embedder, settings, settings_store):
        self.blobs = blobs
        self.index = index
        self.embedder = embedder
        self.settings = settings
        self.settings_store = settings_store
        self.container = settings.container_documents

    # ------------------------------------------------------------------ listing
    def _info(self, blob) -> DocumentInfo:
        meta = blob.metadata or {}
        status = meta.get("status") or QUEUED
        if status not in STATUSES:
            status = QUEUED
        try:
            chunks = int(meta.get("chunks") or 0)
        except ValueError:
            chunks = 0
        return DocumentInfo(
            name=blob.name, doc_id=doc_id_for(blob.name), file_type=file_type_for(blob.name) or "",
            size=blob.size, status=status, error=meta.get("error", ""), chunks=chunks,
            uploaded_at=parse_iso(meta.get("uploaded_at", "")) or blob.last_modified,
            uploaded_by=meta.get("uploaded_by", "") or "storage", indexed_at=parse_iso(meta.get("indexed_at", "")),
            content_hash=meta.get("content_hash", ""),
        )

    def list(self) -> list[DocumentInfo]:
        return [self._info(b) for b in self.blobs.list(self.container)]

    def get(self, name: str) -> DocumentInfo | None:
        try:
            blob = self.blobs.info(self.container, name)
        except ValueError:  # not a valid blob name (for example "../x.pdf")
            return None
        return self._info(blob) if blob else None

    def find(self, doc_id: str, name: str | None = None) -> DocumentInfo | None:
        """Look a document up by id; with ``name`` the lookup needs no listing."""
        if name is not None:
            return self.get(name) if doc_id_for(name) == doc_id else None
        return next((d for d in self.list() if d.doc_id == doc_id), None)

    # ------------------------------------------------------------------ upload
    def upload(self, name: str, fileobj: BinaryIO, size: int, uploaded_by: str) -> UploadResult:
        safe, file_type = validate_upload(name, fileobj, size, self.settings.max_upload_mb)
        digest = sha256_of(fileobj)
        existing = None
        for doc in self.list():
            if doc.name == safe:
                existing = doc
            if doc.content_hash == digest and doc.status not in (FAILED,):
                where = "already indexed" if doc.status == INDEXED else "already uploaded"
                raise UploadError(f"This file is {where} as {doc.name}.")
        self.blobs.put_file(self.container, safe, fileobj, CONTENT_TYPES[file_type], {
            "status": QUEUED, "content_hash": digest, "uploaded_by": uploaded_by, "uploaded_at": now_iso(),
        })
        log.info("Uploaded %s (%s bytes) by %s", safe, size, uploaded_by)
        return UploadResult(safe, doc_id_for(safe), replaced=existing is not None)

    # ------------------------------------------------------------------ state changes
    def _update(self, name: str, changes: dict, if_match: str | None = None) -> str:
        blob = self.blobs.info(self.container, name)
        if blob is None:
            raise FileNotFoundError(name)
        meta = {k: v for k, v in (blob.metadata or {}).items() if v is not None}
        for key, value in changes.items():
            if value is None:
                meta.pop(key, None)
            else:
                meta[key] = str(value)
        return self.blobs.set_metadata(self.container, name, meta, if_match=if_match if if_match else None)

    def mark_queued(self, name: str) -> None:
        self._update(name, {"status": QUEUED, "error": None, "claimed_by": None, "claimed_at": None})

    def is_stale_claim(self, meta: dict) -> bool:
        """A ``processing`` claim whose process is gone (same host, other process) or that is too old."""
        claimed_by = meta.get("claimed_by", "")
        if claimed_by == WORKER_ID:
            return False
        if claimed_by.split(":")[0] == INSTANCE:
            return True  # this host restarted: the claiming process no longer exists
        claimed_at = parse_iso(meta.get("claimed_at", ""))
        limit = timedelta(minutes=self.settings.processing_stale_minutes)
        return claimed_at is None or datetime.now(timezone.utc) - claimed_at > limit

    def needs_processing(self, doc: DocumentInfo, meta: dict, include_finished: bool) -> bool:
        if doc.status == QUEUED:
            return True
        if doc.status == PROCESSING:
            return self.is_stale_claim(meta)
        return include_finished and doc.status in (FAILED, NO_TEXT)

    def pending(self, include_finished: bool = True) -> list[str]:
        """Names to (re)process: everything not indexed, or only new and stale ones (periodic scan)."""
        out = []
        for blob in self.blobs.list(self.container):
            if file_type_for(blob.name) is None:
                continue
            if self.needs_processing(self._info(blob), blob.metadata or {}, include_finished):
                out.append(blob.name)
        return out

    def claim(self, name: str) -> bool:
        blob = self.blobs.info(self.container, name)
        if blob is None:
            return False
        meta = blob.metadata or {}
        if meta.get("status") == PROCESSING and not self.is_stale_claim(meta):
            return False
        if meta.get("status") == INDEXED:
            return False
        try:
            self._update(name, {"status": PROCESSING, "claimed_by": WORKER_ID, "claimed_at": now_iso(),
                                "error": None}, if_match=blob.etag)
        except (PreconditionFailed, FileNotFoundError):
            return False
        return True

    # ------------------------------------------------------------------ processing
    def process(self, name: str) -> str | None:
        """Claim and ingest one document. Returns the final status, or None if it was not claimed."""
        if not self.claim(name):
            return None
        doc_id = doc_id_for(name)
        file_type = file_type_for(name)
        try:
            status, chunks, error, digest = self._ingest(name, doc_id, file_type)
        except FileNotFoundError:
            self.index.delete_document(doc_id)  # deleted while processing
            return None
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the document
            log.exception("Ingestion of %s failed", name)
            try:
                self.index.delete_document(doc_id)
            except Exception:  # noqa: BLE001
                log.warning("Could not remove partial passages of %s", name, exc_info=True)
            status, chunks, error, digest = FAILED, 0, _short_error(exc), None
        changes = {"status": status, "chunks": chunks, "error": error or None, "claimed_by": None,
                   "claimed_at": None, "indexed_at": now_iso() if status == INDEXED else None}
        if digest:
            changes["content_hash"] = digest
        try:
            self._update(name, changes)
        except FileNotFoundError:
            self.index.delete_document(doc_id)
            return None
        log.info("%s: %s (%s passages)", name, status, chunks)
        return status

    def _ingest(self, name: str, doc_id: str, file_type: str | None):
        if not file_type:
            return FAILED, 0, "Unsupported file type.", None
        blob = self.blobs.info(self.container, name)
        if blob is None:
            raise FileNotFoundError(name)
        uploaded_at = parse_iso((blob.metadata or {}).get("uploaded_at", "")) or blob.last_modified
        uploaded_iso = uploaded_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        suffix = "." + {v: k for k, v in FILE_TYPES.items()}[file_type].lstrip(".")
        with tempfile.NamedTemporaryFile(suffix=suffix, prefix="advsearch-") as tmp:
            self.blobs.download_to(self.container, name, tmp)
            tmp.flush()
            digest = sha256_of(tmp)
            try:
                check_content(file_type, tmp)
            except UploadError as exc:
                return FAILED, 0, str(exc), digest
            for other in self.list():
                if other.name != name and other.content_hash == digest and other.status == INDEXED:
                    return FAILED, 0, f"Duplicate content: already indexed as {other.name}.", digest

            self.index.delete_document(doc_id)  # replace any earlier version
            opts = ChunkOptions.from_config(self.settings_store.chunking)
            batch_size = self.settings_store.batch_size
            batch: list = []
            count = 0
            try:
                passages = extract_passages(Path(tmp.name), file_type, opts, self.settings_store.excel)
                for passage in passages:
                    batch.append(passage)
                    if len(batch) >= batch_size:
                        count = self._index_batch(batch, count, doc_id, name, file_type, uploaded_iso)
                        batch = []
                if batch:
                    count = self._index_batch(batch, count, doc_id, name, file_type, uploaded_iso)
            except ExtractionError as exc:
                return FAILED, 0, str(exc), digest
        if count == 0:
            return NO_TEXT, 0, NO_TEXT_MESSAGE, digest
        return INDEXED, count, "", digest

    def _index_batch(self, batch, start, doc_id, name, file_type, uploaded_iso) -> int:
        vectors = self.embedder.embed([p.text for p in batch])
        docs = [{
            "id": f"{doc_id}-{start + i:05d}", "docId": doc_id, "fileName": name, "fileType": file_type,
            "location": p.location, "chunkIndex": start + i, "uploadedAt": uploaded_iso, "content": p.text,
            "contentVector": vec,
        } for i, (p, vec) in enumerate(zip(batch, vectors))]
        self.index.upload(docs)
        return start + len(docs)

    # ------------------------------------------------------------------ admin actions
    def delete(self, name: str) -> int:
        removed = self.index.delete_document(doc_id_for(name))
        self.blobs.delete(self.container, name)
        log.info("Deleted %s (%s passages)", name, removed)
        return removed

    def reindex(self, name: str) -> None:
        self.mark_queued(name)

    def rebuild_index(self) -> list[str]:
        """Drop and recreate the index (needed after an embedding model or dimension change)."""
        self.index.reset()
        names = []
        for doc in self.list():
            if doc.file_type:
                self.mark_queued(doc.name)
                names.append(doc.name)
        return names


def get_document_service() -> DocumentService:
    from . import factory
    from .config import get_settings

    return DocumentService(factory.get_blob_store(), factory.get_index(), factory.get_embedder(), get_settings(),
                           factory.get_settings_store())
