# Vendored front-end libraries

Served from this app (no CDN), so the Content-Security-Policy can stay `script-src 'self'`.

| File | Library | Version | Licence | Source |
|---|---|---|---|---|
| `htmx-2.0.4.min.js` | htmx | 2.0.4 | Zero-Clause BSD (0BSD) | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js |

To update: download the new version, change the file name in `templates/base.html`, and run the UI tests in `qa/tests`.
