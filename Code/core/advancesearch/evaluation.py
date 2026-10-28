"""Search quality of the current index on ``Data/sample_docs/queries.yaml``.

* ``queries``: the expected document must be shown (with the default thresholds, top 3); precision is the share
  of shown documents that are the expected one.
* ``unrelated``: nothing may be shown.
* ``images``: the expected document must be first and show the image with the expected caption.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import get_settings


def _load(path: Path | None = None) -> dict:
    path = path or (get_settings().data_dir or Path("Data")) / "sample_docs" / "queries.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_queries(path: Path | None = None) -> list[dict]:
    return list(_load(path)["queries"])


def evaluate(path: Path | None = None, top: int = 3) -> dict:
    from .search import search

    data = _load(path)
    rows = []
    for q in data["queries"]:
        response = search(q["query"], top_n=top)
        got = [r.file_name for r in response.results]
        rows.append({"query": q["query"], "expected": q["expected"], "kind": q.get("kind", ""), "got": got,
                     "hit": q["expected"] in got, "rank": got.index(q["expected"]) + 1 if q["expected"] in got else None,
                     "match": next((r.match_percent for r in response.results if r.file_name == q["expected"]), None)})
    unrelated = []
    for query in data.get("unrelated") or []:
        got = [r.file_name for r in search(query, top_n=top).results]
        unrelated.append({"query": query, "got": got, "ok": not got})
    images = []
    for q in data.get("images") or []:
        results = search(q["query"], top_n=top).results
        first = results[0] if results else None
        captions = [i.caption for i in first.images] if first else []
        ok = bool(first and first.file_name == q["expected"] and any(c.startswith(q["caption"]) for c in captions))
        images.append({"query": q["query"], "expected": q["expected"], "caption": q["caption"],
                       "got": [r.file_name for r in results], "captions": captions, "ok": ok})
    hits = sum(r["hit"] for r in rows)
    shown = sum(len(r["got"]) for r in rows)
    return {"rows": rows, "hits": hits, "total": len(rows), "accuracy": hits / len(rows) if rows else 0.0,
            "shown": shown, "precision": hits / shown if shown else 0.0, "unrelated": unrelated, "images": images}
