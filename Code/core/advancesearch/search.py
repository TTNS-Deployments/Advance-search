"""Search: retrieve passages, group them by document, score each document and build highlighted snippets.

Match score (also in Documents/user-guide.md and Documents/technical-specification.md):

* Each document is represented by its best passage.
* If the semantic reranker score is available (0 to 4): ``match% = round(rerankerScore / 4 * 100)``,
  ``scoreSource = "semantic"``.
* Otherwise: ``match% = round(clamp(cosine, 0, 1) * 100)`` of the best passage, ``scoreSource = "vector"``.
* Documents below ``min_match_percent`` are not shown. The percentage is a relevance indicator, not a probability.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from .embeddings import STOPWORDS, SynonymMap, stem, words
from .index import Hit

log = logging.getLogger(__name__)

SNIPPET_WORDS = 48
MAX_QUERY_CHARS = 500


@dataclass
class ResultDocument:
    rank: int
    doc_id: str
    file_name: str
    file_type: str
    location: str
    uploaded_at: str
    passage_id: str
    match_percent: int
    score_source: str                      # "semantic" or "vector"
    snippet: list[tuple[str, bool]]        # (text, highlighted) segments, unescaped
    reranker_score: float | None = None
    cosine: float | None = None

    def to_dict(self) -> dict:
        return {
            "rank": self.rank, "docId": self.doc_id, "fileName": self.file_name, "fileType": self.file_type,
            "location": self.location, "uploadedAt": self.uploaded_at, "passageId": self.passage_id,
            "matchPercent": self.match_percent, "scoreSource": self.score_source,
            "rerankerScore": self.reranker_score, "cosine": None if self.cosine is None else round(self.cosine, 4),
            "snippet": "".join(t for t, _ in self.snippet),
            "highlights": [t for t, h in self.snippet if h],
        }


@dataclass
class SearchResponse:
    query: str
    results: list[ResultDocument] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    passages_considered: int = 0
    documents_considered: int = 0
    hidden_below_minimum: int = 0
    top_n: int = 3
    min_match_percent: int = 20

    def to_dict(self) -> dict:
        return {
            "query": self.query, "count": len(self.results), "elapsedSeconds": round(self.elapsed_seconds, 3),
            "passagesConsidered": self.passages_considered, "documentsConsidered": self.documents_considered,
            "hiddenBelowMinimum": self.hidden_below_minimum, "topN": self.top_n,
            "minMatchPercent": self.min_match_percent, "results": [r.to_dict() for r in self.results],
        }


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def match_score(hit: Hit) -> tuple[int, str]:
    """The match percentage and its source for one passage (see the module docstring)."""
    if hit.reranker_score is not None:
        return round(clamp(hit.reranker_score, 0.0, 4.0) / 4.0 * 100), "semantic"
    return round(clamp(hit.cosine or 0.0, 0.0, 1.0) * 100), "vector"


def group_by_document(hits: list[Hit]) -> list[tuple[Hit, int, str]]:
    """Best passage per document, as ``(hit, match_percent, score_source)``, best document first."""
    best: dict[str, tuple[Hit, int, str]] = {}
    for hit in hits:
        percent, source = match_score(hit)
        current = best.get(hit.doc_id)
        if current is None or (percent, hit.score) > (current[1], current[0].score):
            best[hit.doc_id] = (hit, percent, source)
    return sorted(best.values(), key=lambda item: (item[1], item[0].score), reverse=True)


def rank_documents(hits: list[Hit], top_n: int, min_match_percent: int) -> tuple[list[tuple[Hit, int, str]], int, int]:
    grouped = group_by_document(hits)
    kept = [g for g in grouped if g[1] >= min_match_percent]
    return kept[:top_n], len(grouped), len(grouped) - len(kept)


# ---------------------------------------------------------------------------- snippets

def highlight_terms(query: str, related: SynonymMap | None = None) -> tuple[set[str], set[tuple[str, ...]]]:
    """Stemmed query words to highlight, plus related phrases from the same word groups."""
    tokens = words(query)
    singles = {t for t in tokens if t not in STOPWORDS and len(t) >= 3}
    phrases: set[tuple[str, ...]] = set()
    if related is not None:
        for gid in related.concepts(tokens):
            for phrase in related.concept_terms(gid):
                if len(phrase) == 1:
                    if phrase[0] not in STOPWORDS and len(phrase[0]) >= 3:
                        singles.add(phrase[0])
                else:
                    phrases.add(phrase)
    return singles, phrases


def snippet_source(hit: Hit) -> str:
    """Passage text without the context prefix repeated at the start of every passage: the heading path of a
    Word section, or the sheet name of a spreadsheet (both are already shown as the location)."""
    lines = hit.content.split("\n")
    if hit.file_type == "xlsx" and lines and lines[0].startswith("Sheet: "):
        lines = lines[1:]
    elif hit.location.startswith("Section: ") and len(lines) > 1:
        lines = lines[1:]
    return "\n".join(lines)


def build_snippet(content: str, query: str, related: SynonymMap | None = None,
                  max_words: int = SNIPPET_WORDS, keep_lines: bool = False) -> list[tuple[str, bool]]:
    """Highlighted window of the passage. ``keep_lines`` keeps line breaks (spreadsheet rows)."""
    if keep_lines:
        text = "\n".join(" ".join(line.split()) for line in content.split("\n") if line.strip())
    else:
        text = re.sub(r"\s+", " ", content).strip()
    tokens = list(re.finditer(r"[A-Za-z0-9]+", text))
    if not tokens:
        return [(text[:300], False)]
    singles, phrases = highlight_terms(query, related)
    stems = [stem(t.group().lower()) for t in tokens]
    marked = [False] * len(tokens)
    for i, s in enumerate(stems):
        if s in singles:
            marked[i] = True
    for phrase in phrases:
        n = len(phrase)
        for i in range(len(stems) - n + 1):
            if tuple(stems[i:i + n]) == phrase:
                for j in range(i, i + n):
                    marked[j] = True

    # Window of max_words tokens with the most highlighted words (earliest wins ties).
    window = min(max_words, len(tokens))
    best_start, best_count, count = 0, -1, sum(marked[:window])
    best_count = count
    for start in range(1, len(tokens) - window + 1):
        count += marked[start + window - 1] - marked[start - 1]
        if count > best_count:
            best_start, best_count = start, count
    # Start a few words before the first highlight so the snippet reads naturally.
    if best_count > 0:
        first = next(i for i in range(best_start, best_start + window) if marked[i])
        best_start = max(0, min(best_start, first - 6))
    end_token = min(len(tokens), best_start + window) - 1

    start_char = 0 if best_start == 0 else tokens[best_start].start()
    end_char = len(text) if end_token == len(tokens) - 1 else tokens[end_token].end()
    segments: list[tuple[str, bool]] = []
    if start_char > 0:
        segments.append(("… ", False))
    pos = start_char
    for i in range(best_start, end_token + 1):
        if not marked[i]:
            continue
        tok = tokens[i]
        gap = text[pos:tok.start()]
        if segments and segments[-1][1] and gap in ("", " "):
            # Adjacent highlighted words ("annual entitlement") become one mark.
            segments[-1] = (segments[-1][0] + gap + tok.group(), True)
        else:
            if gap:
                segments.append((gap, False))
            segments.append((tok.group(), True))
        pos = tok.end()
    if end_char > pos:
        segments.append((text[pos:end_char], False))
    if end_char < len(text):
        segments.append((" …", False))
    return segments


# ---------------------------------------------------------------------------- entry point

def search(query: str, *, index=None, embedder=None, settings_store=None, top_n: int | None = None,
           min_match_percent: int | None = None) -> SearchResponse:
    from . import factory

    index = index or factory.get_index()
    embedder = embedder or factory.get_embedder()
    settings_store = settings_store or factory.get_settings_store()
    values = settings_store.effective()
    top_n = values["top_n"] if top_n is None else top_n
    minimum = values["min_match_percent"] if min_match_percent is None else min_match_percent

    query = " ".join(query.split())[:MAX_QUERY_CHARS]
    response = SearchResponse(query=query, top_n=top_n, min_match_percent=minimum)
    if not query:
        return response
    started = time.perf_counter()
    vector = embedder.embed_query(query)
    hits = index.search(query, vector, top=settings_store.candidates)
    ranked, considered, hidden = rank_documents(hits, top_n, minimum)
    related = SynonymMap(settings_store.synonyms)
    for rank, (hit, percent, source) in enumerate(ranked, start=1):
        response.results.append(ResultDocument(
            rank=rank, doc_id=hit.doc_id, file_name=hit.file_name, file_type=hit.file_type, location=hit.location,
            uploaded_at=hit.uploaded_at, passage_id=hit.id, match_percent=percent, score_source=source,
            snippet=build_snippet(snippet_source(hit), query, related, keep_lines=hit.file_type == "xlsx"), reranker_score=hit.reranker_score, cosine=hit.cosine,
        ))
    response.passages_considered = len(hits)
    response.documents_considered = considered
    response.hidden_below_minimum = hidden
    response.elapsed_seconds = time.perf_counter() - started
    return response
