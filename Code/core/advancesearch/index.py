"""The passage index: Azure AI Search, or a local SQLite index with the same hybrid behaviour.

Local mode: BM25 keyword ranking (SQLite FTS5) and cosine similarity over the stored vectors, fused with
reciprocal rank fusion (RRF). The semantic reranker is mocked as a blend of the two scores on its 0-4 scale.

Azure mode: one hybrid query (keyword + vector) with the semantic ranker. If the ranker is unavailable
(disabled on the service, quota used up), the result has no reranker scores and a vector-only query supplies
the cosine similarity used for the fallback match score.
"""

from __future__ import annotations

import logging
import math
import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from array import array
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)

RRF_K = 60
SEMANTIC_CONFIG = "default"
VECTOR_PROFILE = "vector-profile"
FIELDS = ["id", "docId", "fileName", "fileType", "location", "chunkIndex", "uploadedAt", "content"]


class IndexMismatch(RuntimeError):
    """The existing index was built for different embedding dimensions; it needs a rebuild."""


@dataclass
class Hit:
    id: str
    doc_id: str
    file_name: str
    file_type: str
    location: str
    chunk_index: int
    uploaded_at: str
    content: str
    score: float = 0.0                       # fused (RRF) score, for ordering only
    reranker_score: float | None = None      # 0-4, semantic ranker (or its local mock)
    cosine: float | None = None              # vector similarity of the passage to the query


@dataclass
class IndexStatus:
    exists: bool
    dimensions: int | None
    configured_dimensions: int
    chunks: int = 0

    @property
    def mismatch(self) -> bool:
        return self.exists and self.dimensions is not None and self.dimensions != self.configured_dimensions

    @property
    def warning(self) -> str:
        if self.mismatch:
            return (f"The search index was built with {self.dimensions}-dimension vectors, but the embedding "
                    f"model is configured for {self.configured_dimensions}. Rebuild the index on the Documents page.")
        return ""


class SearchIndex(ABC):
    dimensions: int

    @abstractmethod
    def ensure(self) -> IndexStatus: ...

    @abstractmethod
    def status(self) -> IndexStatus: ...

    @abstractmethod
    def upload(self, chunks: list[dict]) -> None: ...

    @abstractmethod
    def delete_document(self, doc_id: str) -> int: ...

    @abstractmethod
    def search(self, query: str, vector: list[float], top: int = 50) -> list[Hit]: ...

    @abstractmethod
    def reset(self) -> None: ...


def _rrf(*rankings: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
    return scores


# ---------------------------------------------------------------------------- local

class LocalIndex(SearchIndex):
    def __init__(self, path: Path, dimensions: int, semantic: bool = True):
        self.path = Path(path)
        self.dimensions = dimensions
        self.semantic = semantic
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY, docId TEXT, fileName TEXT, fileType TEXT, location TEXT,
                    chunkIndex INTEGER, uploadedAt TEXT, content TEXT, vector BLOB);
                CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(docId);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content, id UNINDEXED, tokenize='porter unicode61');
            """)
            self._conn = conn
        return self._conn

    def _stored_dimensions(self) -> int | None:
        row = self._db().execute("SELECT value FROM meta WHERE key='dimensions'").fetchone()
        return int(row[0]) if row else None

    def ensure(self) -> IndexStatus:
        with self._lock:
            db = self._db()
            if self._stored_dimensions() is None:
                db.execute("INSERT INTO meta(key, value) VALUES ('dimensions', ?)", (str(self.dimensions),))
                db.commit()
        return self.status()

    def status(self) -> IndexStatus:
        with self._lock:
            exists = self.path.is_file()
            if not exists:
                return IndexStatus(False, None, self.dimensions)
            dims = self._stored_dimensions()
            count = self._db().execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return IndexStatus(dims is not None, dims, self.dimensions, count)

    def _check(self):
        status = self.ensure()
        if status.mismatch:
            raise IndexMismatch(status.warning)

    def upload(self, chunks):
        self._check()
        with self._lock:
            db = self._db()
            for c in chunks:
                vec = array("f", c["contentVector"]).tobytes()
                db.execute("DELETE FROM chunks_fts WHERE id = ?", (c["id"],))
                db.execute("INSERT OR REPLACE INTO chunks VALUES (?,?,?,?,?,?,?,?,?)",
                           (c["id"], c["docId"], c["fileName"], c["fileType"], c["location"], c["chunkIndex"],
                            c["uploadedAt"], c["content"], vec))
                db.execute("INSERT INTO chunks_fts(content, id) VALUES (?, ?)", (c["content"], c["id"]))
            db.commit()

    def delete_document(self, doc_id):
        with self._lock:
            db = self._db()
            ids = [r[0] for r in db.execute("SELECT id FROM chunks WHERE docId = ?", (doc_id,))]
            db.executemany("DELETE FROM chunks_fts WHERE id = ?", [(i,) for i in ids])
            db.execute("DELETE FROM chunks WHERE docId = ?", (doc_id,))
            db.commit()
        return len(ids)

    def document_chunk_count(self, doc_id: str) -> int:
        with self._lock:
            return self._db().execute("SELECT COUNT(*) FROM chunks WHERE docId = ?", (doc_id,)).fetchone()[0]

    def reset(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            for suffix in ("", "-wal", "-shm"):
                Path(f"{self.path}{suffix}").unlink(missing_ok=True)
        self.ensure()

    @staticmethod
    def _match_expression(query: str) -> str:
        from .embeddings import STOPWORDS

        terms = [t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in STOPWORDS]
        return " OR ".join(f'"{t}"' for t in dict.fromkeys(terms))

    @staticmethod
    def mock_reranker(cosine: float, keyword: float) -> float:
        """Stand-in for the semantic ranker (0-4): mostly meaning (cosine), partly exact wording (BM25)."""
        meaning = min(1.0, max(0.0, (cosine - 0.12) / 0.33))
        wording = keyword / (keyword + 6.0) if keyword > 0 else 0.0
        return round(4.0 * min(1.0, 0.75 * meaning + 0.25 * wording), 4)

    def search(self, query, vector, top=50):
        self._check()
        with self._lock:
            db = self._db()
            keyword: dict[str, float] = {}
            expression = self._match_expression(query)
            if expression:
                rows = db.execute("SELECT id, bm25(chunks_fts) AS s FROM chunks_fts WHERE chunks_fts MATCH ? "
                                  "ORDER BY s LIMIT ?", (expression, top)).fetchall()
                keyword = {r[0]: -float(r[1]) for r in rows}
            cosines = self._cosines(db, vector)
        by_vector = sorted(cosines, key=cosines.get, reverse=True)[:top]
        fused = _rrf(sorted(keyword, key=keyword.get, reverse=True), by_vector)
        chosen = sorted(fused, key=fused.get, reverse=True)[:top]
        if not chosen:
            return []
        with self._lock:
            placeholders = ",".join("?" * len(chosen))
            rows = self._db().execute(f"SELECT {', '.join(FIELDS)} FROM chunks WHERE id IN ({placeholders})",
                                      chosen).fetchall()
        hits = []
        for row in rows:
            hit = Hit(*row[:6], uploaded_at=row[6], content=row[7], score=fused[row[0]], cosine=cosines.get(row[0]))
            if self.semantic:
                hit.reranker_score = self.mock_reranker(hit.cosine or 0.0, keyword.get(hit.id, 0.0))
            hits.append(hit)
        key = (lambda h: (h.reranker_score, h.score)) if self.semantic else (lambda h: h.score)
        return sorted(hits, key=key, reverse=True)

    def _cosines(self, db, vector) -> dict[str, float]:
        rows = db.execute("SELECT id, vector FROM chunks").fetchall()
        if not rows:
            return {}
        if len(vector) != self.dimensions:
            raise IndexMismatch(f"Query vector has {len(vector)} dimensions, index expects {self.dimensions}")
        try:
            import numpy as np  # optional speed-up (requirements-dev.txt); the web app does not need it
        except ImportError:
            qn = math.sqrt(sum(v * v for v in vector)) or 1.0
            out = {}
            for key, blob in rows:
                vec = array("f")
                vec.frombytes(blob)
                vn = math.sqrt(sum(v * v for v in vec)) or 1.0
                out[key] = sum(a * b for a, b in zip(vector, vec)) / (qn * vn)
            return out
        matrix = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32).reshape(len(rows), -1)
        q = np.asarray(vector, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(q) or 1.0)
        sims = matrix @ q / np.where(norms == 0, 1.0, norms)
        return {r[0]: float(s) for r, s in zip(rows, sims)}


# ---------------------------------------------------------------------------- Azure AI Search

class AzureSearchIndex(SearchIndex):
    UPLOAD_BATCH = 100
    SEMANTIC_RETRY_SECONDS = 600

    def __init__(self, settings: Settings):
        from azure.search.documents import SearchClient
        from azure.search.documents.indexes import SearchIndexClient

        if not settings.search_endpoint:
            raise RuntimeError("Set SEARCH_ENDPOINT for SEARCH_BACKEND=azure")
        if settings.search_api_key:  # local experiments only; Azure uses the managed identity
            from azure.core.credentials import AzureKeyCredential

            credential = AzureKeyCredential(settings.search_api_key)
        else:
            from .azure_auth import get_credential

            credential = get_credential()
        self.name = settings.search_index_name
        self.dimensions = settings.embedding_dimensions
        self.index_client = SearchIndexClient(settings.search_endpoint, credential)
        self.client = SearchClient(settings.search_endpoint, self.name, credential)
        self._semantic_off_until = 0.0
        self._ensured: IndexStatus | None = None

    def definition(self):
        from azure.search.documents.indexes.models import (
            HnswAlgorithmConfiguration, HnswParameters, SearchableField, SearchField, SearchFieldDataType,
            SearchIndex as IndexModel, SemanticConfiguration, SemanticField, SemanticPrioritizedFields,
            SemanticSearch, SimpleField, VectorSearch, VectorSearchProfile,
        )

        fields = [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True),
            SimpleField(name="docId", type=SearchFieldDataType.String, filterable=True),
            SearchableField(name="fileName", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SimpleField(name="fileType", type=SearchFieldDataType.String, filterable=True, facetable=True),
            SimpleField(name="location", type=SearchFieldDataType.String),
            SimpleField(name="chunkIndex", type=SearchFieldDataType.Int32),
            SimpleField(name="uploadedAt", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
            SearchableField(name="content", type=SearchFieldDataType.String, analyzer_name="en.microsoft"),
            SearchField(name="contentVector", type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                        searchable=True, stored=False, vector_search_dimensions=self.dimensions,
                        vector_search_profile_name=VECTOR_PROFILE),
        ]
        vector = VectorSearch(
            algorithms=[HnswAlgorithmConfiguration(name="hnsw", parameters=HnswParameters(metric="cosine"))],
            profiles=[VectorSearchProfile(name=VECTOR_PROFILE, algorithm_configuration_name="hnsw")],
        )
        semantic = SemanticSearch(default_configuration_name=SEMANTIC_CONFIG, configurations=[
            SemanticConfiguration(name=SEMANTIC_CONFIG, prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="fileName"),
                content_fields=[SemanticField(field_name="content")]))])
        return IndexModel(name=self.name, fields=fields, vector_search=vector, semantic_search=semantic)

    def _existing(self):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self.index_client.get_index(self.name)
        except ResourceNotFoundError:
            return None

    @staticmethod
    def _vector_dims(index) -> int | None:
        for f in index.fields:
            if f.name == "contentVector":
                return f.vector_search_dimensions
        return None

    def ensure(self) -> IndexStatus:
        """Create the index if missing (idempotent). Never changes an index with other vector dimensions."""
        if self._ensured and not self._ensured.mismatch:
            return self._ensured
        existing = self._existing()
        if existing is None:
            self.index_client.create_or_update_index(self.definition())
            log.info("Created search index %s (%s dimensions)", self.name, self.dimensions)
            status = IndexStatus(True, self.dimensions, self.dimensions)
        else:
            status = IndexStatus(True, self._vector_dims(existing), self.dimensions)
            if not status.mismatch and existing.semantic_search is None:
                self.index_client.create_or_update_index(self.definition())
        self._ensured = status
        if status.mismatch:
            log.warning(status.warning)
        return status

    def status(self) -> IndexStatus:
        existing = self._existing()
        if existing is None:
            return IndexStatus(False, None, self.dimensions)
        try:
            count = self.client.get_document_count()
        except Exception:  # noqa: BLE001
            count = 0
        return IndexStatus(True, self._vector_dims(existing), self.dimensions, count)

    def _check(self):
        status = self.ensure()
        if status.mismatch:
            raise IndexMismatch(status.warning)

    def upload(self, chunks):
        self._check()
        for i in range(0, len(chunks), self.UPLOAD_BATCH):
            results = self.client.merge_or_upload_documents(chunks[i:i + self.UPLOAD_BATCH])
            failed = [r for r in results if not r.succeeded]
            if failed:
                raise RuntimeError(f"Search index rejected {len(failed)} passages: {failed[0].error_message}")

    def delete_document(self, doc_id):
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", doc_id):
            raise ValueError("Invalid document id")
        removed = 0
        while True:
            ids = [r["id"] for r in self.client.search(search_text="*", filter=f"docId eq '{doc_id}'",
                                                        select=["id"], top=1000)]
            if not ids:
                return removed
            self.client.delete_documents([{"id": i} for i in ids])
            removed += len(ids)
            if len(ids) < 1000:
                return removed

    def reset(self):
        from azure.core.exceptions import ResourceNotFoundError

        try:
            self.index_client.delete_index(self.name)
        except ResourceNotFoundError:
            pass
        self._ensured = None
        self.ensure()

    def _hybrid(self, query, vector, top, semantic: bool):
        from azure.search.documents.models import VectorizedQuery

        kwargs = dict(search_text=query, top=top, select=FIELDS,
                      vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=top, fields="contentVector")])
        if semantic:
            kwargs.update(query_type="semantic", semantic_configuration_name=SEMANTIC_CONFIG,
                          semantic_error_mode="partial", semantic_max_wait_in_milliseconds=3000)
        return list(self.client.search(**kwargs))

    def search(self, query, vector, top=50):
        from azure.core.exceptions import HttpResponseError
        from azure.search.documents.models import VectorizedQuery

        self._check()
        semantic = time.monotonic() >= self._semantic_off_until
        try:
            rows = self._hybrid(query, vector, top, semantic)
        except HttpResponseError as exc:
            if not semantic or "semantic" not in str(exc).lower():
                raise
            log.warning("Semantic ranker unavailable, using vector scores for %ss: %s",
                        self.SEMANTIC_RETRY_SECONDS, exc)
            self._semantic_off_until = time.monotonic() + self.SEMANTIC_RETRY_SECONDS
            rows = self._hybrid(query, vector, top, False)

        hits = []
        for r in rows:
            reranker = r.get("@search.reranker_score", r.get("@search.rerankerScore"))
            hits.append(Hit(id=r["id"], doc_id=r["docId"], file_name=r["fileName"], file_type=r["fileType"],
                            location=r.get("location") or "", chunk_index=int(r.get("chunkIndex") or 0),
                            uploaded_at=str(r.get("uploadedAt") or ""), content=r.get("content") or "",
                            score=float(r.get("@search.score") or 0.0),
                            reranker_score=float(reranker) if reranker is not None else None))
        if any(h.reranker_score is None for h in hits):
            # Cosine metric: score = 1 / (1 + (1 - cosine))  ->  cosine = 2 - 1 / score
            vector_rows = self.client.search(search_text=None, select=["id"], top=top, vector_queries=[
                VectorizedQuery(vector=vector, k_nearest_neighbors=top, fields="contentVector")])
            cosines = {r["id"]: 2.0 - 1.0 / float(r["@search.score"]) for r in vector_rows if r.get("@search.score")}
            for h in hits:
                h.cosine = cosines.get(h.id)
        return hits
