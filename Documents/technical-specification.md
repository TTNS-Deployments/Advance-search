# Technical Specification

Code: `Code/core/advancesearch` (search engine and ingestion) and `Code/webapp` (Django).

## 1. Supported files and upload rules

| Type | Extension | Checked content | Extraction |
|---|---|---|---|
| PDF | `.pdf` | Starts with `%PDF-` | `pypdf`, page by page. No OCR |
| Word | `.docx` | Zip with `word/document.xml` | `python-docx`: paragraphs and tables in document order, with the heading path |
| Excel | `.xlsx` | Zip with `xl/workbook.xml` | `openpyxl` (`read_only=True`, `data_only=True`), sheet by sheet |

- Maximum size `MAX_UPLOAD_MB` (default 20). Empty files are refused.
- File names are sanitised: folders removed, accents folded to ASCII, unsafe characters replaced, at most 120
  characters, extension kept (lower case). The sanitised name is the blob name.
- A file whose SHA-256 matches an existing document is refused ("This file is already indexed as …").
- A file with the same name as an existing document replaces it (new version, re-indexed).
- Uploads larger than 2 MB are spooled to a temporary file, never held in memory.

## 2. Ingestion

**Status** (blob metadata `status`): `queued` → `processing` → `indexed` | `no_text` | `failed`.

| Metadata key | Meaning |
|---|---|
| `status` | One of the five statuses (a blob without metadata counts as `queued`) |
| `error` | Short error text for `failed`; "No searchable text found. This file may be a scan." for `no_text` |
| `chunks` | Number of passages indexed |
| `content_hash` | SHA-256 of the file |
| `uploaded_by`, `uploaded_at` | Role of the uploader (`storage` when copied in directly) and UTC time |
| `claimed_by`, `claimed_at` | Process holding a `processing` claim (`host:pid:token`) and when |
| `indexed_at` | Time of the last successful indexing |

**Claims.** A process claims a document by replacing its metadata with `status=processing` on the condition that
the ETag it read is still current (`If-Match`). A claim is stale when it belongs to an earlier process on the same
host (restart) or is older than `PROCESSING_STALE_MINUTES` (15).

**Worker.** One daemon thread per process (`INGEST_WORKER=thread`), started on the first request. It processes
one document at a time. Start-up scan and *Sync from storage* queue every document that is not `indexed`;
the periodic scan (`SYNC_INTERVAL_SECONDS`, 300) queues new, queued and stale ones only.

**Passages** (`Config/search.yaml`, `chunking`):

- About 500 tokens (`target_tokens`), never more than 600 (`max_tokens`) or 4,000 characters (`max_chars`).
- Split on paragraphs, then sentences; a sentence longer than the limit is split between words. Never mid-word.
- About 15% overlap (`overlap_ratio`): trailing sentences of a passage start the next one.
- Word: the heading path (for example `Information Security Policy > Lost or stolen devices`) starts every
  passage of a section. Location: `Section: <heading>` (or `Document` without headings).
- PDF: passages do not cross pages. Location: `Page <n>`.
- Excel: rows are grouped, never split or repeated; every passage starts with `Sheet: <name>` and
  `Columns: <header row>`. Empty rows are skipped; hidden sheets are skipped by default (`excel.skip_hidden_sheets`);
  at most `excel.max_rows_per_sheet` rows per sheet. Location: `Sheet '<name>', rows <a>-<b>`.

**Embeddings.** 16 passages per request (`embedding.batch_size`). Azure OpenAI REST API
`POST {endpoint}/openai/deployments/{EMBEDDING_DEPLOYMENT}/embeddings?api-version={AZURE_OPENAI_API_VERSION}` with a
managed-identity token; `dimensions` is sent for `text-embedding-3` models. HTTP 408, 429, 5xx and connection
errors are retried up to 6 times with exponential back-off (honouring `Retry-After`, at most 60 s). A vector of the
wrong size fails the document with a clear error.

**Admin actions.** Re-index (status back to `queued`), delete (all passages with `docId eq '<id>'`, then the blob),
sync from storage, rebuild index (drop and recreate the index, then queue every document).

## 3. Search index

Name `SEARCH_INDEX_NAME` (default `advance-search`), created by the app if missing (idempotent).

| Field | Type | Attributes |
|---|---|---|
| `id` | String | Key: `<docId>-<chunkIndex, 5 digits>` |
| `docId` | String | Filterable. First 32 hex characters of SHA-256 of the blob name |
| `fileName` | String | Searchable (`en.microsoft`); semantic title |
| `fileType` | String | Filterable, facetable: `pdf`, `docx`, `xlsx` |
| `location` | String | Page, section, or sheet and rows |
| `chunkIndex` | Int32 | Order of the passage in the document |
| `uploadedAt` | DateTimeOffset | Filterable, sortable |
| `content` | String | Searchable, `en.microsoft` analyzer; semantic content |
| `contentVector` | Collection(Single) | `EMBEDDING_DIMENSIONS` dimensions, HNSW, cosine, not retrievable |

Vector profile `vector-profile` (HNSW `hnsw`, cosine). Semantic configuration `default` (title `fileName`, content
`content`). If the existing index has a different vector size than `EMBEDDING_DIMENSIONS`, the app does not change
it; Admins see a warning and use *Rebuild index*.

Authentication: the managed identity (`DefaultAzureCredential`). `SEARCH_API_KEY` is only for local experiments.

**Local mode** stores the same fields in SQLite: BM25 keyword ranking with FTS5 (Porter stemming), cosine
similarity over all stored vectors, reciprocal rank fusion (k = 60), and a stand-in for the semantic ranker:
`4 × min(1, 0.75 × clamp((cosine − 0.12) / 0.33) + 0.25 × bm25 / (bm25 + 6))`.

## 4. Match score

1. Retrieve the top 50 passages (`results.candidates`) with one hybrid query.
2. Group them by `docId`; each document keeps its best passage.
3. If the semantic reranker score of that passage is available (`@search.rerankerScore`, 0 to 4):
   `match% = round(rerankerScore / 4 × 100)`, `scoreSource = "semantic"`.
4. Otherwise (ranker disabled, free quota used up, or partial response):
   `match% = round(clamp(cosine, 0, 1) × 100)`, `scoreSource = "vector"`. In Azure the cosine comes from a
   vector-only query of the same vector: with the cosine metric, `@search.score = 1 / (2 − cosine)`.
5. Documents below `min_match_percent` (default 20) are hidden; the rest are sorted by match % and the top
   `top_n` (default 3) are shown.

The percentage is a relevance indicator, not a probability. When the semantic ranker fails with an error, the app
retries without it and does not try it again for 10 minutes.

**Snippet.** A window of about 48 words of the best passage with the most query words (stemmed) and related terms
(`related_terms` in `Config/search.yaml`) highlighted. Text is HTML-escaped; only `<mark>` is added.

## 5. Web app and API

| Route | Method | Roles | Purpose |
|---|---|---|---|
| `/` | GET | Admin, User | Search page; `?q=` renders results on the server |
| `/search/results?q=` | GET (htmx) | Admin, User | Results partial |
| `/documents/<docId>/open/<name>` | GET | Admin, User | Streams the original file (`inline` for PDF) |
| `/documents` | GET | Admin | Documents page |
| `/documents/table` | GET (htmx) | Admin | Table partial; filters `q`, `status`, `type` |
| `/documents/upload` | POST | Admin | Field `file` (repeatable). JSON answer with `Accept: application/json` |
| `/documents/<docId>/reindex`, `/delete` | POST | Admin | Field `name` must match `docId` |
| `/documents/sync`, `/documents/rebuild` | POST | Admin | Sync from storage, rebuild index |
| `/settings` | GET, POST | Admin | Editable settings, `action=reset` |
| `/api/search?q=` | GET | Admin, User | JSON results (below) |
| `/api/documents`, `/api/status` | GET | Admin | Documents with status; counts, queue and system info |
| `/auth/login`, `/auth/logout` | GET/POST, POST | Public | Sign-in, sign-out |
| `/healthz` | GET | Public | Health probe |

Unauthenticated page requests are redirected to sign-in; API requests get 401 JSON; htmx requests get 401 with
`HX-Redirect`. A role without permission gets 403. All POSTs need a CSRF token.

`/api/search` response:

```json
{"query": "how many days off do I get", "count": 3, "elapsedSeconds": 0.21, "topN": 3, "minMatchPercent": 20,
 "passagesConsidered": 50, "documentsConsidered": 12, "hiddenBelowMinimum": 9,
 "results": [{"rank": 1, "docId": "…", "fileName": "Leave-Policy-2026.pdf", "fileType": "pdf",
   "location": "Page 1", "uploadedAt": "2026-10-25T05:41:52Z", "passageId": "…-00000",
   "matchPercent": 77, "scoreSource": "semantic", "rerankerScore": 3.08, "cosine": 0.45,
   "snippet": "…", "highlights": ["annual entitlement", "leave"], "openUrl": "https://…/documents/…"}]}
```

## 6. Testing

| Suite | Command | Covers |
|---|---|---|
| Core | `python -m pytest Code/core` | Extraction, chunking, scoring, local hybrid search on `queries.yaml`, ingestion states and claims, settings, embeddings retry, the Azure AI Search adapter (SDK replaced by fakes), deployment consistency, scripts with a fake `az` |
| Web | `cd Code/webapp && python manage.py test` | Sign-in and lockout, roles on every route, uploads, search output, delete/re-index, downloads, CSRF, headers |
| Browser | `python -m pytest qa/tests` | Playwright against gunicorn in local mode; Blob code against Azurite when it runs |

Results and what was not covered: [qa/TEST_REPORT.md](../qa/TEST_REPORT.md).
