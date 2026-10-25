"""Repository hygiene checks (run by CI and `make lint`).

* every .json file parses
* every relative link in every Markdown file resolves (file and, for Markdown targets, heading anchor)
* no build output, virtual environments, caches or local data are committed
* the wording rules of this repository: no other solutions are mentioned

    python qa/check_repo.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = re.compile(r"(^|/)(__pycache__|\.venv|build|\.localdata|staticfiles|\.pytest_cache)(/|$)")
FORBIDDEN_WORDS = re.compile(r"call.?cent(er|re)|\bcalls\b|\bagents?\b|qa scoring", re.I)
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if (REPO / f).exists()]


def anchors(markdown: str) -> set[str]:
    """GitHub-style heading anchors."""
    found = set()
    for line in markdown.splitlines():
        m = re.match(r"^#{1,6}\s+(.*)", line)
        if m:
            text = re.sub(r"[`*_]|<[^>]+>", "", m.group(1)).strip().lower()
            text = re.sub(r"[^\w\- ]", "", text).replace(" ", "-")
            found.add(text)
    return found


def main() -> int:
    errors: list[str] = []
    files = tracked_files()
    for f in files:
        if FORBIDDEN_PATHS.search(f):
            errors.append(f"must not be committed: {f}")
        path = REPO / f
        if f.endswith(".json"):
            try:
                json.loads(path.read_text())
            except ValueError as exc:
                errors.append(f"invalid JSON: {f}: {exc}")
        if path.suffix in {".pdf", ".docx", ".xlsx", ".png", ".zip"} or "static/vendor/htmx" in f:
            continue
        text = path.read_text(errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if FORBIDDEN_WORDS.search(line) and f != "qa/check_repo.py":
                errors.append(f"wording rule: {f}:{n}: {line.strip()[:100]}")
        if f.endswith(".md"):
            for m in LINK.finditer(text):
                target = m.group(1) or m.group(2)
                if re.match(r"^[a-z]+:", target) or target.startswith("#") and not target[1:]:
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (path.parent / file_part).resolve() if file_part else path
                if not dest.exists():
                    errors.append(f"broken link: {f}: {target}")
                elif anchor and dest.suffix == ".md" and anchor.lower() not in anchors(dest.read_text()):
                    errors.append(f"broken anchor: {f}: {target}")
    for e in errors:
        print(e)
    print(f"{len(files)} files checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
