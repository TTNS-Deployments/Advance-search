"""Split text into overlapping passages on paragraph and sentence boundaries, never mid-word."""

from __future__ import annotations

import re
from dataclasses import dataclass

TOKEN_RE = re.compile(r"\w+|[^\w\s]")
SENTENCE_RE = re.compile(r"(?<=[.!?;:])\s+(?=[\"'(\[]?[A-Z0-9])")


def count_tokens(text: str) -> int:
    """Approximate token count (words and punctuation). Close enough to model tokens for sizing passages."""
    return len(TOKEN_RE.findall(text))


@dataclass(frozen=True)
class ChunkOptions:
    target_tokens: int = 500
    max_tokens: int = 600
    overlap_ratio: float = 0.15
    max_chars: int = 4000

    @classmethod
    def from_config(cls, cfg: dict) -> "ChunkOptions":
        return cls(int(cfg.get("target_tokens", 500)), int(cfg.get("max_tokens", 600)),
                   float(cfg.get("overlap_ratio", 0.15)), int(cfg.get("max_chars", 4000)))


def _units(text: str, opts: ChunkOptions) -> list[str]:
    """Paragraphs, split into sentences, and over-long sentences into word runs."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"[ \t]+", " ", para).strip()
        if not para:
            continue
        sentences = [s.strip() for s in SENTENCE_RE.split(para) if s.strip()]
        for sentence in sentences:
            if count_tokens(sentence) <= opts.max_tokens and len(sentence) <= opts.max_chars:
                units.append(sentence)
                continue
            words, run = sentence.split(), []
            for word in words:
                candidate = " ".join([*run, word])
                if run and (count_tokens(candidate) > opts.target_tokens or len(candidate) > opts.max_chars):
                    units.append(" ".join(run))
                    run = []
                run.append(word[: opts.max_chars])
            if run:
                units.append(" ".join(run))
        units.append("\n")  # paragraph break marker
    return units


def chunk_text(text: str, opts: ChunkOptions | None = None, prefix: str = "") -> list[str]:
    """Return passages of about ``target_tokens`` with ``overlap_ratio`` overlap.

    ``prefix`` (for example a heading or a table header) is repeated at the start of every passage and
    counts towards its size.
    """
    opts = opts or ChunkOptions()
    prefix = prefix.strip()
    budget_tokens = max(50, opts.target_tokens - count_tokens(prefix))
    hard_tokens = max(budget_tokens, opts.max_tokens - count_tokens(prefix))
    budget_chars = max(200, opts.max_chars - len(prefix) - 1)
    overlap_tokens = int(opts.target_tokens * opts.overlap_ratio)

    chunks: list[str] = []
    current: list[str] = []

    def size(parts):
        return sum(count_tokens(p) for p in parts if p != "\n")

    def render(parts):
        body = ""
        for part in parts:
            if part == "\n":
                body = body.rstrip() + "\n\n" if body else body
            else:
                body += ("" if not body or body.endswith("\n") else " ") + part
        body = body.strip()
        return f"{prefix}\n{body}" if prefix else body

    def chars(parts):
        return len(" ".join(parts))

    for unit in _units(text, opts):
        if unit == "\n":
            if current and current[-1] != "\n":
                current.append("\n")
            continue
        tokens = count_tokens(unit)
        if current and (size(current) + tokens > budget_tokens and size(current) > 0
                        or size(current) + tokens > hard_tokens or chars(current) + len(unit) + 1 > budget_chars):
            chunks.append(render(current))
            # Carry trailing sentences into the next passage as overlap.
            tail: list[str] = []
            for part in reversed(current):
                if part == "\n":
                    continue
                if size(tail) + count_tokens(part) > overlap_tokens:
                    break
                tail.insert(0, part)
            current = tail if size(tail) + tokens <= hard_tokens and chars(tail) + len(unit) < budget_chars else []
        current.append(unit)
    if current and size(current):
        chunks.append(render(current))
    return [c for c in chunks if c.strip()]


def chunk_rows(rows: list[tuple[int, str]], opts: ChunkOptions | None = None,
               prefix: str = "") -> list[tuple[int, int, str]]:
    """Group spreadsheet rows into passages of about ``target_tokens``; ``prefix`` (sheet name and header
    row) starts every passage so each row keeps its meaning. Rows are never split or repeated.

    Returns ``(first_row_number, last_row_number, text)`` tuples.
    """
    opts = opts or ChunkOptions()
    budget_tokens = max(50, opts.target_tokens - count_tokens(prefix))
    budget_chars = max(200, opts.max_chars - len(prefix) - 1)
    out: list[tuple[int, int, str]] = []
    group: list[tuple[int, str]] = []
    tokens = chars = 0
    for number, text in rows:
        text = text[:budget_chars]
        t = count_tokens(text)
        if group and (tokens + t > budget_tokens or chars + len(text) + 1 > budget_chars):
            out.append((group[0][0], group[-1][0], prefix + "\n" + "\n".join(r for _, r in group)))
            group, tokens, chars = [], 0, 0
        group.append((number, text))
        tokens += t
        chars += len(text) + 1
    if group:
        out.append((group[0][0], group[-1][0], prefix + "\n" + "\n".join(r for _, r in group)))
    return out
