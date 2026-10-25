# Test cases

Scope: everything in this repository that runs without Azure. Layers: **Core** (the `advancesearch` package,
`Code/core/tests`), **Web** (Django, `Code/webapp/portal/tests.py`), **UI** (Playwright in headless Chromium against
gunicorn in local mode, `qa/tests/test_ui.py`), **Storage** (Blob code against the Azurite emulator,
`qa/tests/test_azurite.py`) and **Deploy** (template, parameters and scripts). Browser tests are named after
these IDs (`test_UI05_...`).

## Core and deployment (pytest, `Code/core/tests`)

| ID | Layer | Priority | Area | Test file | Expected result |
|---|---|---|---|---|---|
| C-01 | Core | High | PDF extraction | `test_extract_chunk.py` | Passages per page with `Page n`; no text for an image-only PDF; corrupt PDF raises a clear error |
| C-02 | Core | High | Word extraction | `test_extract_chunk.py` | Heading path repeated in each passage, `Section: <heading>`, tables included, empty file gives nothing |
| C-03 | Core | High | Excel extraction | `test_extract_chunk.py` | Header row repeated in every passage, real row numbers, empty rows and hidden sheets skipped (option to include) |
| C-04 | Core | High | Chunking | `test_extract_chunk.py` | ≤ 600 tokens and ≤ 4,000 characters, about 15% overlap, never mid-word, paragraph/sentence boundaries, rows never split |
| C-05 | Core | Critical | Match score | `test_search.py` | `round(reranker/4×100)` (semantic), `round(clamp(cosine)×100)` fallback (vector), clamping, per-document best passage, minimum %, top N |
| C-06 | Core | High | Snippets | `test_search.py` | Query and related words highlighted, adjacent words merged, window with ellipses, raw text left for template escaping |
| C-07 | Core | Critical | Search quality | `test_search_quality.py` | Every query in `queries.yaml` (keyword, paraphrase, Excel row) finds its document in the top 3; unrelated query shows nothing |
| C-08 | Core | Critical | Ingestion states | `test_ingest.py` | queued → processing → indexed; failed with error; no_text; partial passages removed after an embeddings failure |
| C-09 | Core | High | Duplicates and versions | `test_ingest.py` | Same content refused ("already indexed as …"), also when dropped into storage; same name replaces |
| C-10 | Core | Critical | Claims and recovery | `test_ingest.py` | ETag claim stops a second process; restart recovery (same host), stale claim, live claim skipped; sync rules |
| C-11 | Core | High | Delete, re-index, rebuild | `test_ingest.py` | Delete removes blob and every passage (filter on docId); rebuild empties index and re-queues all |
| C-12 | Core | High | Worker thread | `test_ingest.py` | Start-up scan indexes files dropped in storage; queue de-duplicates |
| C-13 | Core | Medium | Upload validation | `test_ingest.py` | Wrong type, magic bytes, renamed Office files, size, empty, odd names sanitised |
| C-14 | Core | High | Settings store | `test_services.py` | Defaults from `search.yaml`, overrides in `config/settings.json`, validation, broken file ignored |
| C-15 | Core | High | Embeddings | `test_services.py` | Mock deterministic and meaning-aware; Azure client retries 429/5xx/connection errors with back-off, not 4xx, gives up after 6, checks dimensions |
| C-16 | Core | High | Azure AI Search adapter | `test_services.py` | Index schema and semantic config; reranker scores used; cosine fallback from a vector query; retry without semantic; delete by filter; dimension mismatch warning |
| C-17 | Core | Medium | CLI | `test_search_quality.py` | seed, search, status, reset (needs `--yes`) |
| D-01 | Deploy | Critical | Template consistency | `test_deployment.py` | Parameter files match the template (names, types, allowed values, ranges); portal form outputs are parameters with allowed options |
| D-02 | Deploy | Critical | App settings | `test_deployment.py` | Every setting in the brief is set; every variable the code reads is set or documented as optional; secrets are Key Vault references; every variable is in `configuration.md` |
| D-03 | Deploy | High | Shared plan, roles, network | `test_deployment.py` | Plan created only without `existingAppServicePlanId`; 7 role assignments; private endpoints and DNS zones for the four services |
| D-04 | Deploy | High | No secrets | `test_deployment.py` | No GUIDs (other than built-in role IDs and test placeholders) or e-mail addresses in the repository |
| D-05 | Deploy | Critical | deploy.sh demo flow | `test_scripts.py` | With a fake `az`: RG reused, plan looked up and passed by ID, deployer OID from token, password passed, code step after infra, run-from-package SAS, 1 worker/4 threads, samples uploaded before restart, no Graph, Kudu or data-plane requests |
| D-06 | Deploy | High | Failure paths | `test_scripts.py` | Plan not found stops before deploying; provider registration and its failure; missing outputs; no storage key; failed deployment stops; argument errors |
| D-07 | Deploy | Medium | Script hygiene | `test_scripts.py` | `bash -n`, shellcheck, executable, `--help` |

## Web app (Django, `manage.py test`)

| ID | Layer | Priority | Area | Expected result |
|---|---|---|---|---|
| W-01 | Web | Critical | Sign-in | Wrong password 403 (×5), then 429 even with the right password; right password signs in with the chosen role; empty configured password refused (503, "not configured"); unknown role 400 |
| W-02 | Web | Critical | Lockout address | Counted per client address from the right-most `X-Forwarded-For` entry; a forged prefix does not reset it |
| W-03 | Web | Critical | Roles | Users get 403 on every Admin page, action and API; navigation hides Admin pages; Admin reaches everything |
| W-04 | Web | Critical | Unauthenticated | Pages redirect to sign-in, API 401 JSON, htmx 401 with `HX-Redirect`, POST actions redirect; `/healthz` public |
| W-05 | Web | High | Uploads | Valid file indexed; wrong type, magic bytes, too large, duplicate refused with messages; odd names sanitised; scan shows No text; works without JavaScript |
| W-06 | Web | Critical | Search output | Top 3, rank, match %, score source, reranker formula, highlights, location, open URL; partial renders cards, meter, popover; empty, no-match, no-documents and error states; escaping |
| W-07 | Web | High | Document actions | Delete removes passages and results; re-index; mismatched name 404; sync; rebuild; filters |
| W-08 | Web | High | Download | Streams the original bytes with type, disposition, length, no-store; unknown or tampered IDs 404 |
| W-09 | Web | High | Settings | Save, effect on search, reset, validation error 400 |
| W-10 | Web | Critical | CSRF and headers | POSTs without token 403; real form token works; strict CSP, `X-Frame-Options`, `nosniff`; no inline scripts, styles or handlers in templates |

## Browser (Playwright, `qa/tests/test_ui.py`)

| ID | Priority | Area | Expected result |
|---|---|---|---|
| UI01 | Critical | Admin sign-in | Admin navigation (Search, Documents, Settings), role chip |
| UI02 | Critical | User sign-in | No Admin navigation; Documents page and API refused (403) |
| UI03 | High | Wrong password, sign out | Error shown, role choice kept; sign-out returns to sign-in |
| UI04 | Low | Password reveal | Toggle shows the password, `aria-pressed` updates |
| UI05 | Critical | Upload | File uploaded with progress, row appears, becomes *Indexed* by polling, then found by search |
| UI06 | High | Upload validation | Wrong type refused in the browser; fake PDF refused by the server |
| UI07 | Medium | Status chips | Scan shows *No text* with its message; others *Indexed* |
| UI08 | Medium | Filters | Type and name filters update the table |
| UI09 | Critical | Delete | Confirmation dialog: cancel keeps, confirm deletes; document gone from results |
| UI10 | High | Re-index, sync | Re-index returns to *Indexed*; sync reports |
| UI11 | High | Open document | Streams the original PDF through the app, no storage URL |
| UI12 | Critical | Queries | Six sample queries return their document in the top 3 |
| UI13 | Critical | Result cards | Rank, file icon, badge, location, highlighted snippet, meter width = %, tooltip with source, sorted scores |
| UI14 | Medium | Meter colour | Colour follows the value |
| UI15 | High | Copy link, popover | Link copied to clipboard with toast; popover opens and closes with Escape |
| UI16 | High | No close match | Friendly state with three tips |
| UI17 | High | Keyboard, examples, recent | `/` focuses, Enter searches and updates the URL, recent searches stored, example chip runs, clear button clears |
| UI18 | Medium | Deep link | `/?q=` renders results on the server, meters animate |
| UI19 | High | Settings | Number of results applies; validation error; reset |
| UI20 | Medium | Theme | Toggle switches theme, label updates, choice persists after reload |
| UI21 | High | Responsive | No horizontal overflow at 375 px on sign-in, results, Documents, Settings |
| UI22 | High | Accessibility sanity | `lang`, one `h1`, every field labelled, every button and link named, SVGs labelled or hidden, no duplicate IDs (5 pages) |
| UI23 | Medium | Focus order | Tab order skip link → wordmark → nav; visible focus ring |
| UI24 | Low | Reduced motion | Transitions off when the user prefers reduced motion |
| UI25 | High | Security headers | Strict CSP and frame headers in the browser; password never in the page |
| — | Critical | Console | Every UI test fails if the page logs a JavaScript error, a warning (CSP included) or a failed load other than the 4xx a test asks for |

## Storage (Azurite, `qa/tests/test_azurite.py`)

| ID | Priority | Area | Expected result |
|---|---|---|---|
| AZ01 | Critical | Blob backend end to end | Upload, ingest, status metadata (`indexed`, `no_text`), search, download through `AzureBlobStore` |
| AZ02 | Critical | Conditional claim | `If-Match` with a stale ETag fails; a second claim is refused |
| AZ03 | High | Settings and delete | Overrides saved in the config container; delete removes blob and passages |

## Not covered (needs Azure)

ARM deployment, Azure AI Search queries and the semantic ranker, Azure OpenAI embeddings, managed-identity access,
Key Vault references, App Service run-from-package start-up, VNet integration and private endpoints, the Cloud
Shell run of the scripts, GitHub Actions deployment.
