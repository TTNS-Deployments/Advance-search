# Project progress and context

Read this first when continuing work in a new session. Keep it updated after each piece of work.
Last updated: 2026-10-25 (stage 0: repository cleaned, plan written).

## What this is

Advance Search: an Azure web app that makes PDF, Word and Excel documents searchable by meaning. Admins upload
documents; text is extracted, split into passages, embedded with Azure OpenAI and indexed in Azure AI Search.
A search combines keyword, vector and semantic ranking and returns the top documents with a match score.

Repository: https://github.com/TTNS-Deployments/Advance-search, branch `main`. Work happens in a GitHub
Codespace, which **cannot sign in to Azure**. Deployment runs from **Azure Cloud Shell (Bash)**, where only
management-API (`https://management.azure.com`) tokens work.

## Task list

| # | Stage | Status |
|---|---|---|
| 0 | Remove legacy files, write this file | Done |
| 1 | Core package `advancesearch` (config, storage, extract, chunk, embeddings, index, search, ingest, worker, settings, CLI) + tests | Planned |
| 2 | Sample documents (PDF, DOCX, XLSX) + `queries.yaml` + accuracy test | Planned |
| 3 | Django web app (sign-in, Search, Documents, Settings) + web tests | Planned |
| 4 | ARM template (Bicep source compiled to JSON), parameter files, portal form, consistency tests | Planned |
| 5 | Deployment scripts (`deploy.sh`, `deploy_code_arm.sh`, `package.sh`) + fake-`az` tests | Planned |
| 6 | Playwright UI tests, screenshots, architecture diagram, `qa/` report | Planned |
| 7 | Documentation, README, CI workflows | Planned |
| 8 | Final checks, push | Planned |

## Decisions

- Layout, conventions and patterns follow the agreed reference structure (Code/core, Code/webapp, Config, Data,
  Deployment, Documents, qa, imgs).
- Python 3.12, Django 5.2, gunicorn, whitenoise, htmx (vendored). No relational database, signed-cookie sessions.
- Ingestion runs inside the web app (one background thread per process). No Function app, no database: document
  status lives in blob metadata.
- Sign-in: one shared demo password plus a role choice (Admin or User). Entra ID is a roadmap item.

## Next steps

Build stage 1.
