"""Top-3 accuracy of the current index on ``Data/sample_docs/queries.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import get_settings


def load_queries(path: Path | None = None) -> list[dict]:
    path = path or (get_settings().data_dir or Path("Data")) / "sample_docs" / "queries.yaml"
    return list(yaml.safe_load(path.read_text(encoding="utf-8"))["queries"])


def evaluate(path: Path | None = None, top: int = 3) -> dict:
    from .search import search

    rows = []
    for q in load_queries(path):
        response = search(q["query"], top_n=top, min_match_percent=0)
        got = [r.file_name for r in response.results]
        rows.append({"query": q["query"], "expected": q["expected"], "kind": q.get("kind", ""), "got": got,
                     "hit": q["expected"] in got, "rank": got.index(q["expected"]) + 1 if q["expected"] in got else None,
                     "match": next((r.match_percent for r in response.results if r.file_name == q["expected"]), None)})
    hits = sum(r["hit"] for r in rows)
    return {"rows": rows, "hits": hits, "total": len(rows), "accuracy": hits / len(rows) if rows else 0.0}
