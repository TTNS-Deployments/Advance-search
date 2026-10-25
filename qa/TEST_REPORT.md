# Test report: Advance Search (local verification)

**Verdict: everything that can run without Azure passes. Nothing has been run on Azure yet.**

All automated suites pass with no failures: 129 core tests (including the 19-query search-quality check, the
deployment consistency checks and the scripts against a fake `az`), 55 web tests, 37 browser tests and 3 tests of
the Blob Storage code against the Azurite emulator. The deployable package was built with `package.sh --vendor`
and run with gunicorn the way App Service runs it: sign-in, upload, background indexing and search worked.

## Environment

| | |
|---|---|
| Mode | `ADVSEARCH_MODE=local`: folder storage (Azurite for the AZ tests), SQLite hybrid index, mock embeddings, `AUTH_MODE=password` in browser tests |
| Branch | `main` |
| Python | 3.12.3 (`.venv`) |
| Tools | Django 5.2.18, pytest 9, Playwright 1.64.1 (Chromium headless), Bicep CLI 0.48.1, shellcheck 0.11, Azurite 3.33.0 |
| OS | Linux (GitHub Codespace, no Azure sign-in possible) |
| Date | 2026-10-25 |
| Data | Every suite uses its own temporary data folder |

## Totals

| Suite | Command | Passed | Failed | Skipped |
|---|---|---|---|---|
| Core + deployment | `python -m pytest Code/core` | 129 | 0 | 0 |
| Web app | `cd Code/webapp && python manage.py test` | 55 | 0 | 0 |
| Browser (Playwright) | `python -m pytest qa/tests` (UI) | 37 | 0 | 0 |
| Storage (Azurite) | `python -m pytest qa/tests` (AZ, Azurite running) | 3 | 0 | 0 |
| **All** | | **224** | **0** | **0** |

Other checks:

| Check | Result |
|---|---|
| `shellcheck` and `bash -n` on the three scripts | No findings |
| Bicep: `azuredeploy.bicep` compiles, matches the committed `azuredeploy.json`, `bicep lint` | Pass, no warnings |
| `qa/check_repo.py`: JSON validity, every relative Markdown link and anchor, no build output or caches committed, wording rules | Pass |
| Search quality (`python -m advancesearch eval`, all 13 sample documents) | 19/19 queries have the expected document in the top 3 (18 at rank 1, 1 at rank 2) |
| `package.sh --vendor` | `build/webapp.zip`, 24 MB, 5,992 files, static files collected, no numpy, tests excluded |
| Package smoke test (system Python 3.12, libraries only from `.packages`, gunicorn 1 worker × 4 threads) | `/healthz` ok, sign-in 302, upload accepted and indexed by the worker thread, search returned the leave policy (75%, semantic) |
| Docker image (`docker compose up --build`) | Builds and serves the app; the seed container could not reach Azurite because this Codespace blocks traffic between containers, so the Blob code was tested from the host instead (AZ01–AZ03) |

Evidence logs: [`qa/evidence/`](evidence) (`core_pytest.log`, `web_tests.log`, `qa_pytest.log`, `lint.log`,
`eval.log`, `package_smoke.log`).

## Defects found and fixed during testing

| Found by | Problem | Fix |
|---|---|---|
| UI17 | Clicking the clear (×) button sometimes did nothing: the `/` hint reappeared when the search box lost focus and moved the button between mouse-down and mouse-up | The hint is hidden with `visibility` (no layout change) |
| UI21 | Documents page was 694 px wide at 375 px: a visually hidden label escaped the table's scroll container | Scroll container is `position: relative` |
| UI12 | The confirmation dialog's `autofocus` produced a browser warning on every page | `autofocus` removed (the dialog focuses its first button itself) |
| Web tests | Templates did not receive `user`, and an invalid blob name in an open link raised an error instead of 404 | Context processor adds `user`; invalid names return 404 |
| Visual review | Word snippets repeated the heading path; spreadsheet rows ran together | Snippets drop the prefix already shown as the location; Excel rows keep their line breaks |

## Not covered (needs Azure)

These parts have **not** been run and are verified only by static checks, unit tests with fakes, or emulators:

- The ARM deployment itself (template validity is checked by the Bicep compiler and the consistency tests only).
- Azure AI Search: index creation, hybrid queries, the semantic ranker and its fallback (adapter tested with the SDK
  replaced by fakes).
- Azure OpenAI embeddings and quota (client tested with a fake HTTP session).
- Managed-identity access, role assignments, Key Vault references.
- App Service start-up from `WEBSITE_RUN_FROM_PACKAGE` (the same package ran under gunicorn locally).
- The scripts in Cloud Shell (tested against a fake `az`), GitHub Actions deployment, private networking (prod).
- Search quality with real embeddings: the 19/19 result uses the local mock; Azure results will differ.
