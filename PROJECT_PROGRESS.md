# Project progress and context

Read this first when continuing work in a new session. Keep it updated after each piece of work.
Last updated: 2026-10-25 (phase 1 built and verified locally; ready for the first demo deployment from Cloud Shell).

## What this is

Advance Search: an Azure web app that makes PDF, Word and Excel documents searchable by meaning. Admins upload
documents; text is extracted, split into passages, embedded with Azure OpenAI and indexed in Azure AI Search. A
hybrid search (keyword + vector + semantic ranker) returns the top 3 documents with a match score.

Repository: https://github.com/TTNS-Deployments/Advance-search, branch `main`. Work happens in a GitHub Codespace,
which **cannot sign in to Azure**. Deployment runs from **Azure Cloud Shell (Bash)**, where only
management-API (`https://management.azure.com`) tokens work.

## Status

| # | Stage | Status |
|---|---|---|
| 0 | Remove legacy files, progress file | Done |
| 1 | Core package `advancesearch` + tests | Done |
| 2 | Sample documents (13: 4 PDF, 4 DOCX, 4 XLSX, 1 scan) + 19 evaluation queries | Done: 19/19 in top 3 locally |
| 3 | Django web app (sign-in, Search, Documents, Settings, API) + web tests | Done |
| 4 | ARM template (Bicep source + compiled JSON), parameter files, portal form, consistency tests | Done (not deployed) |
| 5 | `deploy.sh`, `deploy_code_arm.sh`, `package.sh` + fake-`az` tests | Done (not run in Cloud Shell) |
| 6 | Playwright tests, Azurite tests, screenshots, architecture diagram, `qa/` report | Done |
| 7 | Documentation, README, CI workflows | Done |
| 8 | First demo deployment | **Ran successfully 2026-10-25** from Cloud Shell (infrastructure, code, sample upload). In-app checks pending |

Test totals (2026-10-25): core 129, web 55, browser 37, Azurite 3 — all pass. Details: `qa/TEST_REPORT.md`.

## What was verified locally, and what is untested on Azure

Verified in the Codespace: the whole app in local mode; the built package (`package.sh --vendor`) running under
gunicorn with system Python 3.12 (sign-in, upload, background indexing, search); the Blob Storage code against
Azurite (metadata, ETag claims, settings blob, delete); the scripts against a fake `az` (success and failure
paths); the template with the Bicep compiler, `bicep lint` and consistency tests; Docker image build.

Untested (needs Azure): the ARM deployment, Azure AI Search (index creation, hybrid query, semantic ranker), Azure
OpenAI embeddings and quota, managed identity and role assignments, Key Vault references, App Service run from
package, the Cloud Shell run of the scripts, GitHub Actions deployment, private networking (prod), search quality
with real embeddings.

## Decisions

- Layout: `Code/core` (package), `Code/webapp` (Django), `Config`, `Data`, `Deployment`, `Documents`, `qa`, `imgs`.
- Python 3.12, Django 5.2, gunicorn, whitenoise, htmx 2.0.4 vendored, hand-written CSS, no CDN. No relational
  database (`DATABASES = {}`), signed-cookie sessions. Strict CSP (`script-src 'self'`, no inline scripts or style
  attributes; the meters are sized from JavaScript).
- Ingestion inside the web app: one background thread per process, started on the first request; status in blob
  metadata; ETag-conditional claims; start-up and periodic scans (`SYNC_INTERVAL_SECONDS`=300). No Function app.
- Duplicate content dropped straight into storage is marked `failed` with "Duplicate content: already indexed as …"
  (the five statuses stay as specified); the upload page refuses it up front.
- A same-name upload replaces the earlier version (re-indexed).
- Start-up scan and *Sync from storage* re-queue everything not `indexed` (including `failed` and `no_text`); the
  periodic scan only picks up new, queued and stale ones, so failed files are not retried every 5 minutes.
- Match score exactly as specified; in Azure the cosine for the fallback comes from a vector-only query
  (`cosine = 2 − 1/@search.score`). If the semantic ranker errors, the app retries without it and skips it for 10 minutes.
- Local mock: hashed words + `related_terms` groups + character trigrams; the local "semantic ranker" is
  `4 × (0.75 × meaning + 0.25 × wording)`. The `related_terms` list also highlights related words in snippets in all
  modes. The mock's tuning only matters for local mode.
- Template authored in Bicep (`Deployment/ARM/azuredeploy.bicep`) and compiled to `azuredeploy.json`. CI checks the
  compiled JSON matches the source. The decompile-then-build round trip of the JSON fails with decompiler errors
  (BCP034, a decompiler limitation with looped resources), so CI does not use it.
- Embedding deployment default `GlobalStandard` (assumption; confirm with the model check below and change only
  the parameter if needed). API version `2024-10-21`.
- Search semantic setting is omitted on the free tier (not supported there).
- Lockout counts per client address using the **right-most** `X-Forwarded-For` entry (the one App Service adds), so a
  client cannot reset the counter by sending its own header.
- `demo.env`: `SEED=1` (the demo uploads the 13 sample documents; the web app indexes them after the restart).
- Names: `<prefix>-<env>-<suffix>-<role>`, suffix = 6 characters of `uniqueString(resourceGroup().id, prefix, env)`;
  storage `advsrch<env><suffix>st`. Deployment name `advsrch-<env>`.
- The demo web app joins the existing plan `ccai-demo-gqausd-web-plan` (looked up by name at deployment time; no
  subscription ID in the repo); the plan is never modified. gunicorn 1 worker × 4 threads.
- Sign-in: shared demo password + role choice, documented as demo-only; Entra ID is a roadmap item.
- Branding (user's request, 2026-10-25): the Tata Tele Business Services logo
  (`Code/webapp/static/img/ttbs-logo.png`) sits in the header next to the "Advance Search" wordmark and on the
  sign-in card. In the dark theme it has a white backing, because its dark lettering is invisible on dark grey.

## Commands for the user (Azure Cloud Shell, Bash)

1. Register the search provider and check the embedding model and quota in South India (once):

```bash
az provider register -n Microsoft.Search --wait
az cognitiveservices model list -l southindia --query "[?contains(model.name,'embedding')].{n:model.name,v:model.version,s:model.skus[].name}" -o table
az cognitiveservices usage list -l southindia -o table
```

   Expected: `text-embedding-3-small`, version `1`, with `GlobalStandard` among the SKUs, and at least 10 free in the
   matching usage line. If the output differs, change only `embeddingModelVersion`, `embeddingDeploymentSku` or
   `embeddingCapacity` in `Deployment/ARM/parameters/demo.parameters.json` (commit and push), not the code.

2. Deploy (choose the password yourself; keep the single quotes):

```bash
cd ~ && git clone https://github.com/TTNS-Deployments/Advance-search.git ; cd ~/Advance-search && git pull && Deployment/scripts/deploy.sh -e demo --param demoPassword='<choose-a-password>'
```

3. Open the printed URL, sign in as Admin, wait for the sample documents to show *Indexed*, search
   `how many days off do I get`.

## Demo deployment (2026-10-25)

- Command: `Deployment/scripts/deploy.sh -e demo --param demoPassword='...'` in Cloud Shell; every step finished.
- Pre-checks: `text-embedding-3-small` v1 offers GlobalStandard in South India; quota
  `OpenAI.GlobalStandard.text-embedding-3-small` 0 / 1000 used (demo uses 10).
- Web app: `advsrch-demo-i5iesm-web` on the shared plan `ccai-demo-gqausd-web-plan`,
  https://advsrch-demo-i5iesm-web.azurewebsites.net. Storage `advsrchdemoi5iesmst`. Resource suffix `i5iesm`.
- `az deployment group create` printed the generic Azure CLI warning "This output may compromise security by
  showing secrets"; nothing secret is in the outputs (the password is a secure parameter).
- Still to confirm in the app: sign-in, sample documents reach *Indexed*, search results and match %.

## Open items

- First real deployment: watch for `InsufficientQuota`, role-assignment propagation (documents failing with
  401/403 → Re-index after a few minutes), and the first start-up time on the shared B1 plan.
- Check search quality with real embeddings on the 19 sample queries (`/api/search`), and tune `min_match_percent`.
- dev and prod untested; prod code deployment needs a path from inside the VNet.
- Phase 2: Entra ID sign-in with real roles and per-department access, OCR, more file types, answer generation.
