# Configuration Reference

## Where each setting comes from

| Source | Used for | Changed by |
|---|---|---|
| ARM parameters (`Deployment/ARM/parameters/<env>.parameters.json`) | SKUs, sizes, regions, model, sign-in mode | Editing the file and running `deploy.sh` |
| Web app settings (environment variables, set by the template) | Endpoints, names, limits, secrets as Key Vault references | The template (every infrastructure deployment resets them) |
| Key Vault | `demo-password`, `django-secret-key` | `--param demoPassword='...'`; the Django key is regenerated on each infrastructure deployment |
| `Config/search.yaml` (in the package) | Defaults for results and the search page, passage sizes, Excel options, related terms | Editing the file and redeploying the code |
| `settings.json` in the `config` container | Admin overrides: number of results, minimum match %, relative cutoff %, example queries, welcome text | The **Settings** page (no redeploy) |
| `.env` (local only) | Local development | You; read by the `make` targets |

All settings come from environment variables. A value that is an unresolved Key Vault reference (the literal text
`@Microsoft.KeyVault(...)`) is treated as empty.

## Search engine (`advancesearch` package: web app and CLI)

| Variable | Default | Set by the template | Meaning |
|---|---|---|---|
| `ADVSEARCH_MODE` | `local` | `azure` | Default for every backend below: `local` or `azure` |
| `ENVIRONMENT_NAME` | `local` / `azure` | `environmentName` | Shown in the footer and on the Settings page |
| `STORAGE_BACKEND` | from mode | – | `local` (folder) or `azure` (Blob Storage or Azurite) |
| `LOCAL_DATA_DIR` | `<repo>/.localdata` | – | Local storage folder and SQLite index |
| `AZURE_STORAGE_ACCOUNT_URL` | – | Blob endpoint | Storage account, accessed with the managed identity |
| `AZURE_STORAGE_CONNECTION_STRING` | – | – | Instead of the URL, for Azurite or key-based local tests |
| `CONTAINER_DOCUMENTS` | `documents` | `documents` | Container with the original files and their status metadata |
| `CONTAINER_CONFIG` | `config` | `config` | Container with `settings.json` |
| `CONTAINER_IMAGES` | `extracted-images` | `extracted-images` | Container with the images extracted from documents (`<docId>/<imageId>.<ext>` and `<docId>/images.json`) |
| `SEARCH_BACKEND` | from mode | – | `local` (SQLite hybrid search) or `azure` (Azure AI Search) |
| `SEARCH_ENDPOINT` | – | `https://<search>.search.windows.net` | Azure AI Search endpoint |
| `SEARCH_API_KEY` | – | – | Admin key for local experiments only; Azure uses the managed identity |
| `SEARCH_INDEX_NAME` | `advance-search` | `searchIndexName` | Index name (created by the app) |
| `EMBEDDING_BACKEND` | from mode (`mock` locally) | – | `mock` or `azure` |
| `AZURE_OPENAI_ENDPOINT` | – | Azure OpenAI endpoint | Embeddings resource |
| `AZURE_OPENAI_KEY` | – | – | API key for local experiments only; Azure uses the managed identity |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | `openAiApiVersion` | Embeddings API version |
| `EMBEDDING_DEPLOYMENT` | `text-embedding-3-small` | Deployment name (= model name) | Embedding deployment |
| `EMBEDDING_DIMENSIONS` | `1536` | `embeddingDimensions` | Vector size of the index and the model; a change needs **Rebuild index** |
| `MAX_UPLOAD_MB` | `20` | `maxUploadMb` | Largest upload |
| `SEARCH_MIN_MATCH_PERCENT` | – (`search.yaml`: 30) | – | Overrides `results.min_match_percent` (0–100). The Settings page overrides this |
| `SEARCH_RELATIVE_CUTOFF_PERCENT` | – (`search.yaml`: 60) | – | Overrides `results.relative_cutoff_percent` (0–100, 0 = off). The Settings page overrides this |
| `IMAGE_EXTRACTION` | `on` | – | `off` stops extracting images from new and re-indexed documents |
| `IMAGE_OCR` | `auto` | – | `auto`: read text in images when `pytesseract` and the `tesseract` program are installed; `off`: never |
| `INGEST_WORKER` | `thread` | – | `thread` (background thread), `inline` (tests) or `off` |
| `SYNC_INTERVAL_SECONDS` | `300` | – | How often the worker looks for new files in storage |
| `PROCESSING_STALE_MINUTES` | `15` | – | When a `processing` claim of another instance counts as abandoned |
| `AZURE_CLIENT_ID` | – | – | Client ID of a user-assigned managed identity (empty = system-assigned) |
| `ADVSEARCH_CONFIG_DIR` | `Config` next to the package | – | Folder with `search.yaml` |
| `ADVSEARCH_SAMPLE_DATA_DIR` | `Data` next to the package | – | Folder with `sample_docs` (CLI `seed` and `eval`) |
| `WEBSITE_INSTANCE_ID` | – | Set by App Service | Identifies the instance in ingestion claims |

## Web app only

| Variable | Default | Set by the template | Meaning |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | dev key in local mode | Key Vault reference `django-secret-key` | Signs sessions; required outside local mode |
| `AUTH_MODE` | `dev` locally, `password` in Azure | `authMode` (`password`) | `password`: role choice + shared password. `dev`: role choice only, refused outside local mode |
| `DEMO_PASSWORD` | – | Key Vault reference `demo-password` | The shared password. Empty = sign-in refused ("not configured") |
| `DISPLAY_TIME_ZONE` | `Asia/Kolkata` | `displayTimeZone` | Time zone of dates on the pages |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | – | Application Insights | Enables telemetry (OpenTelemetry) |
| `DJANGO_DEBUG` | `false` | – | Django debug pages; developer machines only |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | – | Extra host names (the App Service host name is added automatically) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | – | – | Extra trusted origins (custom domains) |
| `WEBSITE_HOSTNAME` | – | Set by App Service | Added to the allowed hosts and trusted origins |
| `DJANGO_SSL_REDIRECT` | `true` outside local mode | – | Redirect HTTP to HTTPS |
| `CONTENT_SECURITY_POLICY` | strict, `'self'` only | – | Overrides the Content-Security-Policy header |
| `LOG_LEVEL` | `INFO` | – | Root log level |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | – | `false` | No build on the server (the package includes every library) |
| `PYTHONPATH` | – | `/home/site/wwwroot/.packages` | Where the packaged libraries are |
| `WEBSITE_RUN_FROM_PACKAGE` | – | Set by `deploy_code_arm.sh` | SAS URL of the code package |

## `Config/search.yaml`

| Key | Default | Editable on Settings | Meaning |
|---|---|---|---|
| `results.top_n` | 3 | Yes (1–10) | Most documents shown per search (fewer when fewer really match) |
| `results.min_match_percent` | 30 | Yes (0–100) | Documents below this match % are hidden (env `SEARCH_MIN_MATCH_PERCENT`) |
| `results.relative_cutoff_percent` | 60 | Yes (0–100) | Documents below this % of the best document's match % are hidden; 0 = off (env `SEARCH_RELATIVE_CUTOFF_PERCENT`) |
| `results.strong_reranker_score` | 2.0 | No | A document without any query keyword is shown only if a passage scores at least this with the semantic ranker (0–4) |
| `results.strong_cosine` | 0.45 | No | The same, when the semantic ranker is unavailable: cosine similarity of at least this |
| `results.candidates` | 50 | No | Passages retrieved before grouping by document |
| `welcome_text` | (text) | Yes (≤ 500 characters) | Shown under the title on the search page |
| `example_queries` | 5 queries | Yes (≤ 12, one per line) | Suggestion chips under the search bar |
| `chunking.target_tokens` | 500 | No | Aimed passage size |
| `chunking.max_tokens` | 600 | No | Largest passage |
| `chunking.overlap_ratio` | 0.15 | No | Share of a passage repeated at the start of the next |
| `chunking.max_chars` | 4000 | No | Hard character cap per passage |
| `excel.skip_hidden_sheets` | true | No | Ignore hidden sheets |
| `excel.max_rows_per_sheet` | 20000 | No | Rows read per sheet |
| `embedding.batch_size` | 16 | No | Passages per embeddings request |
| `images.enabled` | true | No | Extract embedded images from PDF, Word and Excel files |
| `images.min_width`, `images.min_height` | 50, 50 | No | Smaller images (icons, bullets) are skipped, in pixels (and in points on a PDF page) |
| `images.max_aspect_ratio` | 12 | No | Thinner images (rules, borders) are skipped |
| `images.repeated_pages` | 3 | No | An image repeated on this many pages or sections is a logo or watermark and is skipped (0 = keep) |
| `images.max_per_document` | 100 | No | Images kept per document |
| `images.context_lines` | 3 | No | Lines (Word: paragraphs, Excel: rows) above and below an image indexed with it |
| `images.max_text_chars` | 2000 | No | Longest indexed text per image |
| `images.ocr` | auto | No | `auto` or `off`; see `IMAGE_OCR` |
| `related_terms` | 34 groups | No | Groups of related words: used by the local mock embeddings and to highlight related words in snippets |

Changes to the non-editable keys apply after a code redeploy; chunking and image changes apply to documents
indexed afterwards (use **Rebuild index**, or `python -m advancesearch reindex --keep-index`, to apply them to all).

Precedence of the two relevance thresholds: the **Settings** page, then the environment variable, then
`search.yaml`.

## ARM parameters

The full list with demo, dev and prod values and the accepted options is in
[Deployment/README.md](../Deployment/README.md#sku-and-sizing-parameters).
