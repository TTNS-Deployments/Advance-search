# Security

## Reporting a vulnerability

Do **not** open a public issue for security problems. Raise a ticket marked *Security* through the support channel
in [SUPPORT.md](SUPPORT.md), with the steps to reproduce and the potential impact.

## How Advance Search protects documents

| Area | Control |
|---|---|
| Sign-in | **Demo only:** one shared password (in Key Vault) and a role choice (Admin or User). Five wrong passwords per client address block sign-in for 15 minutes; with no password configured, sign-in is refused. Anyone with the password can choose Admin, so use it only for demonstrations. Entra ID sign-in with real roles is planned |
| Authorisation | Role checks on every page and API route; Users cannot reach upload, delete, re-index, sync, rebuild or settings |
| Service access | The web app's **system-assigned managed identity** with least-privilege roles (Storage Blob Data Contributor, Cognitive Services OpenAI User, Search Index Data Contributor, Search Service Contributor, Key Vault Secrets User). No service keys in app settings |
| Secrets | The demo password and the Django secret key are in **Key Vault**, read through Key Vault references |
| Documents | Private containers (no public blob access). Files are opened only through the app, after a role check; links require sign-in |
| Uploads | Extension, magic bytes and Office zip structure checked; size limit; names sanitised; streamed to temporary files; duplicates refused |
| Web | HTTPS only, TLS 1.2, FTP and basic-auth publishing off, secure and HTTP-only cookies, CSRF protection, strict Content-Security-Policy (no inline scripts, vendored libraries), `X-Frame-Options: DENY`, HSTS, escaped output |
| Network (prod) | Private endpoints for Blob, AI Search, Azure OpenAI and Key Vault with public access disabled; web app VNet integration |
| Monitoring | Application Insights and Log Analytics. Microsoft Defender for Cloud is not enabled by the template |

## Known limitations

- The shared demo password is not a substitute for individual accounts. There is no audit trail per person.
- Every signed-in user can search every document (no per-department access yet).
- Sign-in failure counters are kept per app process; with several instances each counts separately.
- Storage account keys are enabled in demo and dev (`allowSharedKeyAccess=true`) so code can be deployed from Cloud
  Shell. prod disables them.
