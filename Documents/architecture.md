# Architecture

Advance Search is one web app plus four Azure data services, deployed by one ARM template
([`Deployment/ARM/azuredeploy.json`](../Deployment/ARM/azuredeploy.json)).

![Architecture](../imgs/architecture.svg)

## 1. Components

| Component | Azure service | Role |
|---|---|---|
| Web app | App Service (Linux, Python 3.12), gunicorn 1 worker × 4 threads | Django pages (Search, Documents, Settings), JSON API, demo sign-in, upload validation, the ingestion worker thread, hybrid search and scoring, document streaming |
| Document store | Blob Storage, container `documents` | Original files. Each blob's **metadata** holds its status, error, passage count, content hash, uploader and dates. There is no database |
| Settings store | Blob Storage, container `config` | `settings.json`: the admin's overrides of `Config/search.yaml` |
| Code packages | Blob Storage, container `code-packages` | The zipped app the web app runs from (`WEBSITE_RUN_FROM_PACKAGE`) |
| Embeddings | Azure OpenAI, its own resource in `openAiLocation` (South India) | One embedding deployment (`text-embedding-3-small`, 1536 dimensions). No chat model |
| Search index | Azure AI Search | One index of passages: text (`en.microsoft` analyzer), vector (HNSW, cosine), semantic configuration. Created by the app |
| Secrets | Key Vault (RBAC) | `demo-password`, `django-secret-key`, read through App Service Key Vault references |
| Monitoring | Application Insights on Log Analytics | Requests, exceptions and logs (OpenTelemetry) |

## 2. Data flow

**Upload and ingestion**

1. An Admin drops files on the Documents page. The app checks extension, magic bytes, zip structure (Word and
   Excel) and size, sanitises the name, computes a SHA-256 hash, refuses duplicates and writes the blob with
   `status=queued`.
2. The worker thread claims the document: it replaces the metadata with `status=processing` only if the blob's
   ETag is unchanged, so a second process cannot claim it too.
3. The blob is streamed to a temporary file. Text is extracted page by page (PDF), section by section with the
   heading path (Word) or sheet by sheet with the header row repeated (Excel), and split into passages of about
   500 tokens with 15% overlap.
4. Passages are embedded 16 at a time (retry with back-off on 429 and 5xx) and uploaded to the index. Earlier
   passages of the same document are removed first.
5. The metadata becomes `indexed` (with the passage count), `no_text` or `failed` (with the error).

**Search**

1. The query is embedded and sent as one hybrid request: keyword search, vector search (k = 50) and the semantic
   ranker over the top 50 passages.
2. Passages are grouped by document; each document is scored by its best passage (see
   [Technical specification, section 4](technical-specification.md#4-match-score)).
3. The top N documents (default 3) above the minimum match % are shown with a highlighted snippet. *Open
   document* streams the original blob through the app.

**Recovery.** On start-up, on *Sync from storage* and every `SYNC_INTERVAL_SECONDS`, the worker scans the
container. Files without a status (copied in directly, for example by `deploy.sh --seed`), queued files and
`processing` claims left by a process that no longer exists are queued again.

## 3. Security

- Users sign in with a shared demo password and a role choice (Admin or User), stored in a signed session cookie.
  Five wrong passwords from one address block sign-in for 15 minutes. This is for demos only; Entra ID is on the
  roadmap.
- The web app's system-assigned managed identity has Storage Blob Data Contributor, Cognitive Services OpenAI
  User, Search Index Data Contributor, Search Service Contributor and Key Vault Secrets User. No keys are stored in
  app settings.
- Documents are never exposed by a public URL: blob public access is off and *Open document* streams through the
  app after a role check.
- HTTPS only, TLS 1.2, FTP off, secure cookies, CSRF protection, a strict Content-Security-Policy (no inline
  scripts), HSTS.
- Production (`privateNetworking=true`): private endpoints for Blob, AI Search, Azure OpenAI and Key Vault, public
  access disabled on all four, web app VNet integration with all outbound traffic through the VNet. The web app
  stays reachable on its public HTTPS endpoint.

## 4. Scaling and cost

| Lever | Effect |
|---|---|
| `searchSku`, `searchReplicas`, `searchPartitions` | Query throughput, availability (2+ replicas for read SLA) and index size. Basic holds 15 GB per partition |
| `searchSemanticSearch` | `free` gives 1,000 semantic queries a month; after that results fall back to vector scores automatically. `standard` is billed per 1,000 queries |
| `embeddingCapacity` | Tokens per minute for ingestion and queries. Ingestion of large libraries is the main consumer |
| `webAppSku`, `webAppInstanceCount` | Each instance runs one ingestion thread; claims keep instances from duplicating work |

The demo shares an existing B1 plan (1 vCPU, 1.75 GB), so the app runs one gunicorn worker, processes one file at
a time and never holds more than one file in memory.

## 5. Environments

| Environment | Plan | Search | Network | Notes |
|---|---|---|---|---|
| demo | Existing shared B1 plan | Basic, semantic free | Public endpoints | Deployed from Cloud Shell; verified locally only |
| dev | Own B1 plan | Basic, semantic free | Public endpoints | Untested on Azure |
| prod | Own P0v3 plan, 2 instances | Standard, 2 replicas, semantic standard | Private endpoints | Untested on Azure; code deployment must run from inside the network |

Each environment has its own resource names (`<prefix>-<env>-<suffix>-<role>`), so several can share a resource
group without colliding.
