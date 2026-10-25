# Local Development

Local mode needs no Azure account: storage is a folder, the index is SQLite with a local hybrid search, and
embeddings are a deterministic mock.

## Setup

Python 3.12 is recommended (the version App Service runs).

```bash
make setup                         # .venv + requirements-dev.txt (includes Code/core in editable mode)
make seed                          # index Data/sample_docs (13 files; one is a scan and shows "No text")
make run                           # http://localhost:8000
```

Sign-in locally uses `AUTH_MODE=dev`: choose Admin or User, no password. To try the demo password flow, put
`AUTH_MODE=password` and `DEMO_PASSWORD=...` in `.env`.

## How local mode works

| Part | Local implementation | File |
|---|---|---|
| Storage | Folder `.localdata/storage/<container>`; metadata in `.localdata/storage/.meta`, ETags and a file lock for claims | `advancesearch/storage.py` |
| Index | SQLite `.localdata/index.sqlite3`: FTS5 BM25 (Porter stemming) + cosine over all vectors, fused with reciprocal rank fusion | `advancesearch/index.py` |
| Semantic ranker | A stand-in on the same 0–4 scale: 75% meaning (cosine), 25% wording (BM25) | `LocalIndex.mock_reranker` |
| Embeddings | Hashed words, related-term groups (`related_terms` in `Config/search.yaml`) and character trigrams; deterministic | `advancesearch/embeddings.py` |
| Worker | Same background thread as in Azure | `advancesearch/worker.py` |

`numpy` (in `requirements-dev.txt`) speeds up the local cosine step; without it a pure-Python loop is used. The
web app package never includes numpy.

The mock is tuned so that every query in `Data/sample_docs/queries.yaml` finds its expected document in the top 3
(`make eval`). It is not a language model: results on your own documents will differ from Azure OpenAI.

## Useful commands

| Command | What it does |
|---|---|
| `python -m advancesearch seed` | Upload and index the sample documents |
| `python -m advancesearch ingest <file-or-folder>` | Upload and index files |
| `python -m advancesearch search "<query>" [--top N]` | Print the top documents with match %, source and snippet |
| `python -m advancesearch status` | List documents and their status |
| `python -m advancesearch eval` | Top-3 accuracy on `queries.yaml` |
| `python -m advancesearch reindex` | Rebuild the index and process every document |
| `python -m advancesearch reset --yes` | Delete all documents, the index and settings overrides |
| `make test` / `make test-ui` / `make lint` | Core and web tests / browser tests / shellcheck, JSON and link checks |
| `make package` | Build `build/webapp.zip` with every library (as deployed) |
| `make screenshots` | Regenerate `imgs/screenshot-*.png` |
| `python Data/sample_docs/generate.py` | Regenerate the sample documents (deterministic) |

## Using real Azure services from your machine

Swap one service at a time; the rest stay local. Sign in with `az login` (your identity needs the same data roles
as the web app), or use keys for quick experiments:

```bash
# real embeddings, local storage and index (rebuild the local index when the dimensions change)
export EMBEDDING_BACKEND=azure AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com EMBEDDING_DEPLOYMENT=text-embedding-3-small
python -m advancesearch reindex

# real Azure AI Search as well (use a separate index name, never the demo's)
export SEARCH_BACKEND=azure SEARCH_ENDPOINT=https://<service>.search.windows.net SEARCH_INDEX_NAME=advance-search-dev
python -m advancesearch seed
```

## Browser tests and screenshots

```bash
.venv/bin/python -m playwright install --with-deps chromium   # once
make test-ui
```

The tests start the app with gunicorn on a free port with its own data folder, so your `.localdata` is not
touched. The Azurite tests in `qa/tests/test_azurite.py` run only when Azurite listens on port 10000:

```bash
docker run -d --rm -p 10000:10000 mcr.microsoft.com/azure-storage/azurite:3.33.0 azurite-blob --blobHost 0.0.0.0 --skipApiVersionCheck --loose
```

## Docker

`make docker-up` builds the image and runs the web app with the Azurite blob emulator (real Azure Storage SDK,
local index and mock embeddings), then seeds the sample documents. Open http://localhost:8000. Stop with
`make docker-down`. In environments that block traffic between containers, the seed step cannot reach Azurite;
run the app with `make run` instead.

## Code map

| Path | Contents |
|---|---|
| `Code/core/advancesearch/config.py` | Settings from environment variables |
| `factory.py` | Builds the configured storage, index, embeddings and settings store |
| `extract.py`, `chunk.py` | Text extraction (PDF, Word, Excel) and passage splitting |
| `embeddings.py` | Mock and Azure OpenAI embeddings |
| `index.py` | Local and Azure AI Search indexes |
| `search.py` | Grouping, match score, snippets |
| `ingest.py`, `worker.py` | Upload validation, status state machine, background worker |
| `settings_store.py` | `Config/search.yaml` plus admin overrides |
| `cli.py`, `evaluation.py` | Command line and the accuracy report |
| `Code/webapp/accounts` | Demo sign-in, roles, middleware, decorators |
| `Code/webapp/portal` | Views, JSON API, template tags, tests |
| `Code/webapp/templates`, `static` | Pages, CSS, JavaScript, vendored htmx |
