# Configuration Reference

## Where each setting comes from

| Source | Used for | Changed by |
|---|---|---|
| ARM parameters (`Deployment/ARM/parameters/<env>.parameters.json`) | SKUs, sizes, regions, model, sign-in mode | Editing the file and running `deploy.sh` |
| Web app settings (environment variables, set by the template) | Endpoints, names, limits, secrets as Key Vault references | The template (every infrastructure deployment resets them) |
| Key Vault | `demo-password`, `django-secret-key` | `--param demoPassword='...'`; the Django key is regenerated on each infrastructure deployment |
| `Config/search.yaml` (in the package) | Defaults for results and the search page, passage sizes, Excel options, related terms | Editing the file and redeploying the code |
| `settings.json` in the `config` container | Admin overrides: number of results, minimum match %, example queries, welcome text | The **Settings** page (no redeploy) |
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
| `results.top_n` | 3 | Yes (1–10) | Documents shown per search |
| `results.min_match_percent` | 20 | Yes (0–100) | Documents below this match % are hidden |
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
| `related_terms` | 34 groups | No | Groups of related words: used by the local mock embeddings and to highlight related words in snippets |

Changes to the non-editable keys apply after a code redeploy; chunking changes apply to documents indexed
afterwards (use **Rebuild index** to apply them to all).

## ARM parameters

The full list with demo, dev and prod values and the accepted options is in
[Deployment/README.md](../Deployment/README.md#sku-and-sizing-parameters).
