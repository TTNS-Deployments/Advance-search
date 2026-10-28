"""Search: retrieve passages, group them by document, score each document, keep only the documents that really
match and build highlighted snippets and the matching images.

Match score (also in Documents/user-guide.md and Documents/technical-specification.md):

* Each document is represented by its best passage (a text passage or the text of one of its images).
* If the semantic reranker score is available (0 to 4): ``match% = round(rerankerScore / 4 * 100)``,
  ``scoreSource = "semantic"``.
* Otherwise: ``match% = round(clamp(cosine, 0, 1) * 100)`` of the best passage, ``scoreSource = "vector"``.
* Exact wording counts: a passage (or file name) that contains the whole query as a phrase gets
  ``EXACT_BONUS`` points (at most 100%). A query that names something specific (a "quoted phrase", a code such as
  ``FT-200``, a label such as ``figure 3`` or a file name such as ``wiring-diagram.png``) only matches documents
  that contain it; when the query is only that name, a passage that contains it scores at least ``NAMED_FLOOR``.
* Evidence: a document is shown only if its best passage is genuinely relevant in meaning (semantic ranker score
  of at least ``strong_reranker_score``, 2.0 = "relevant" on the ranker's 0-4 scale; or, without the ranker, cosine
  similarity of at least ``strong_cosine``) **or** it contains at least one keyword of the query (or a related
  term). Vector search always returns the nearest passages, even when none is related, and the ranker gives such
  passages about 1-2 ("somewhat relevant", 25-50%); without this rule they would be shown.
* Precision: documents below ``min_match_percent`` are dropped, then documents below ``relative_cutoff_percent``
  of the best document's match %, then at most ``top_n`` are shown. Nothing is padded: no match means no result.
  The percentage is a relevance indicator, not a probability.
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
EXACT_BONUS = 10
NAMED_FLOOR = 50
LABEL_RE = re.compile(r"\b(fig(?:ure)?|table|chart|diagram|exhibit|illustration)\.?\s*(\d+[a-z]?)\b", re.IGNORECASE)
IMAGES_PER_RESULT = 4
TOKEN_RE = re.compile(r"[a-z0-9]+")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9]+(?:[-_./][A-Za-z0-9]+)*")   # FT-200, sm3_v2, wiring-diagram.png


@dataclass
class ResultImage:
    image_id: str
    doc_id: str
    location: str
    page: int | None
    caption: str
    alt_text: str
    original_name: str
    width: int
    height: int
    format: str
    match_percent: int

    @property
    def label(self) -> str:
        from .images import meaningful_name

        name = self.original_name if meaningful_name(self.original_name) else ""
        return self.caption or self.alt_text or name or "Image"

    def to_dict(self) -> dict:
        return {"imageId": self.image_id, "docId": self.doc_id, "location": self.location, "page": self.page,
                "caption": self.caption, "altText": self.alt_text, "originalName": self.original_name,
                "label": self.label, "width": self.width, "height": self.height, "format": self.format,
                "matchPercent": self.match_percent}


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
    exact_match: bool = False              # the best passage or the file name contains the query as a phrase
    matched_terms: list[str] = field(default_factory=list)   # query keywords (or related terms) in the document
    images: list[ResultImage] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rank": self.rank, "docId": self.doc_id, "fileName": self.file_name, "fileType": self.file_type,
            "location": self.location, "uploadedAt": self.uploaded_at, "passageId": self.passage_id,
            "matchPercent": self.match_percent, "scoreSource": self.score_source, "exactMatch": self.exact_match, "matchedTerms": self.matched_terms,
            "rerankerScore": self.reranker_score, "cosine": None if self.cosine is None else round(self.cosine, 4),
            "snippet": "".join(t for t, _ in self.snippet),
            "highlights": [t for t, h in self.snippet if h],
            "images": [i.to_dict() for i in self.images],
        }


NO_MATCH_MESSAGE = "No matching documents found."


@dataclass
class SearchResponse:
    query: str
    results: list[ResultDocument] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    passages_considered: int = 0
    documents_considered: int = 0
    hidden_below_minimum: int = 0
    hidden_below_relative: int = 0
    hidden_not_exact: int = 0
    hidden_no_evidence: int = 0
    top_n: int = 3
    min_match_percent: int = 30
    relative_cutoff_percent: int = 60

    @property
    def hidden(self) -> int:
        """Documents that matched some words of the query but not well enough to be shown."""
        return self.hidden_below_minimum + self.hidden_below_relative + self.hidden_not_exact + self.hidden_no_evidence

    def to_dict(self) -> dict:
        body = {
            "query": self.query, "count": len(self.results), "elapsedSeconds": round(self.elapsed_seconds, 3),
            "passagesConsidered": self.passages_considered, "documentsConsidered": self.documents_considered,
            "hiddenBelowMinimum": self.hidden_below_minimum, "hiddenBelowRelative": self.hidden_below_relative,
            "hiddenNotExact": self.hidden_not_exact, "hiddenNoEvidence": self.hidden_no_evidence, "topN": self.top_n, "minMatchPercent": self.min_match_percent,
            "relativeCutoffPercent": self.relative_cutoff_percent, "results": [r.to_dict() for r in self.results],
        }
        if not self.results:
            body["message"] = NO_MATCH_MESSAGE
        return body


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def match_score(hit: Hit) -> tuple[int, str]:
    """The match percentage and its source for one passage (see the module docstring)."""
    if hit.reranker_score is not None:
        return round(clamp(hit.reranker_score, 0.0, 4.0) / 4.0 * 100), "semantic"
    return round(clamp(hit.cosine or 0.0, 0.0, 1.0) * 100), "vector"


# ---------------------------------------------------------------------------- exact wording

def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class QueryTerms:
    phrase: tuple[str, ...]                  # the query without leading and trailing stopwords
    specific: tuple[tuple[str, ...], ...]    # quoted phrases, codes and file names: a match must contain them
    only_named: bool = False                 # the query is nothing but those names ("FT-200", "figure 3")


def analyse_query(query: str) -> QueryTerms:
    specific = [tuple(tokens(q)) for q in re.findall(r'"([^"]+)"', query) if tokens(q)]
    for label, number in LABEL_RE.findall(re.sub(r'"[^"]*"', " ", query)):  # "figure 3", "Fig. 2", "table 4"
        specific.append(("figure" if label.lower().startswith("fig") else label.lower(), number.lower()))
    for raw in re.sub(r'"[^"]*"', " ", query).split():
        raw = raw.strip(".,;:!?()[]{}'")
        parts = tuple(tokens(raw))
        if not parts or not IDENTIFIER_RE.fullmatch(raw):
            continue
        code = len(raw) >= 3 and any(c.isdigit() for c in raw) and any(c.isalpha() for c in raw)  # FT-200, SM3
        file_name = len(parts) >= 2 and re.search(r"\.[A-Za-z][A-Za-z0-9]{1,4}$", raw) is not None
        if code or file_name:
            specific.append(parts)
    phrase = tokens(query)
    while phrase and phrase[0] in STOPWORDS:
        phrase.pop(0)
    while phrase and phrase[-1] in STOPWORDS:
        phrase.pop()
    named = {w for term in specific for w in term} | {"fig"}
    only_named = bool(specific) and all(w in named or w in STOPWORDS for w in tokens(query))
    return QueryTerms(tuple(phrase), tuple(dict.fromkeys(specific)), only_named)


def contains(haystack: list[str], needle: tuple[str, ...]) -> bool:
    """``needle`` appears as consecutive words; "FT200" also matches "FT-200" and the other way round."""
    if not needle:
        return False
    n, joined = len(needle), "".join(needle)
    for i, word in enumerate(haystack):
        if word == needle[0] and tuple(haystack[i:i + n]) == needle:
            return True
        if joined.startswith(word):
            acc = word
            for nxt in haystack[i + 1:i + 4]:
                if acc == joined or len(acc) >= len(joined):
                    break
                acc += nxt
            if acc == joined:
                return True
    return False


@dataclass
class Scored:
    """One passage with its match % (including the exact-phrase bonus)."""
    hit: Hit
    percent: int
    source: str
    exact: bool
    specific: frozenset[int]              # which of the query's specific terms the passage (or file name) contains


def score_hits(hits: list[Hit], terms: QueryTerms) -> list[Scored]:
    out = []
    name_cache: dict[str, list[str]] = {}
    for hit in hits:
        percent, source = match_score(hit)
        content = tokens(hit.content)
        name = name_cache.setdefault(hit.file_name, tokens(hit.file_name))
        exact = len(terms.phrase) >= 2 and (contains(content, terms.phrase) or contains(name, terms.phrase))
        found = frozenset(i for i, t in enumerate(terms.specific) if contains(content, t) or contains(name, t))
        if exact:
            percent = min(100, percent + EXACT_BONUS)
        if terms.specific and len(found) == len(terms.specific):  # contains everything the query names
            exact = True
            percent = max(percent, NAMED_FLOOR) if terms.only_named else min(100, percent + EXACT_BONUS)
        out.append(Scored(hit, percent, source, exact, found))
    return out


# ---------------------------------------------------------------------------- ranking

# Query words that say nothing about the topic, so finding them in a document is no evidence of a match.
FILLER = frozenset(stem(w) for w in """document documents file files find show need want information info detail details
please tell know give look looking search searching anything something thing things""".split())


@dataclass(frozen=True)
class Evidence:
    """Thresholds for a "genuinely relevant in meaning" passage (``Config/search.yaml``, ``results``)."""
    reranker: float = 2.0
    cosine: float = 0.45


def query_keywords(query: str) -> list[str]:
    """Stemmed topic words of the query: no stopwords, fillers or one- and two-letter words."""
    return list(dict.fromkeys(w for w in words(query) if w not in STOPWORDS and w not in FILLER and len(w) >= 3))


def strong_meaning(scored: Scored, evidence: Evidence) -> bool:
    hit = scored.hit
    if hit.reranker_score is not None:
        return hit.reranker_score >= evidence.reranker
    return (hit.cosine or 0.0) >= evidence.cosine


@dataclass
class RankedDocument:
    best: Scored
    passages: list[Scored]                # every passage of the document that was retrieved, best first
    images: list[Scored] = field(default_factory=list)
    matched_terms: list[str] = field(default_factory=list)

    @property
    def percent(self) -> int:
        return self.best.percent


@dataclass
class Ranking:
    documents: list[RankedDocument]
    considered: int = 0
    hidden_below_minimum: int = 0
    hidden_below_relative: int = 0
    hidden_not_exact: int = 0
    hidden_no_evidence: int = 0


def keyword_matches(doc: RankedDocument, keywords: dict[str, str], query_concepts: set[int],
                    related: SynonymMap | None) -> list[str]:
    """Query keywords (as typed) or related-term groups found in the document's retrieved passages or file name.

    ``keywords`` maps each stemmed keyword to the word the user typed."""
    found: list[str] = []
    name = set(words(doc.best.hit.file_name))
    texts = [words(s.hit.content) for s in doc.passages]
    for kw, typed in keywords.items():
        if kw in name or any(kw in t for t in texts):
            found.append(typed)
    if related is not None and query_concepts:
        for t in texts:
            for gid in sorted(query_concepts & set(related.concepts(t))):
                label = " ".join(related.concept_terms(gid)[0])
                if label not in found:
                    found.append(label)
    return found


def rank_documents(hits: list[Hit], top_n: int, min_match_percent: int, relative_cutoff_percent: int = 0,
                   query: str = "", evidence: Evidence | None = None,
                   related: SynonymMap | None = None) -> Ranking:
    """One entry per document (its best passage), best first, keeping only the documents that really match."""
    terms = analyse_query(query)
    by_doc: dict[str, list[Scored]] = {}
    for scored in score_hits(hits, terms):
        by_doc.setdefault(scored.hit.doc_id, []).append(scored)
    docs = []
    for passages in by_doc.values():
        passages.sort(key=lambda s: (s.percent, s.hit.score), reverse=True)
        docs.append(RankedDocument(passages[0], passages))
    docs.sort(key=lambda d: (d.percent, d.best.hit.score), reverse=True)
    ranking = Ranking([], considered=len(docs))

    if evidence is not None and query:  # no shared keyword and no strong meaning match: not a match at all
        typed = {stem(w): w for w in reversed(TOKEN_RE.findall(query.lower()))}
        keywords = {kw: typed.get(kw, kw) for kw in query_keywords(query)}
        concepts = set(related.concepts(words(query))) if related is not None else set()
        backed = []
        for d in docs:
            d.matched_terms = keyword_matches(d, keywords, concepts, related)
            if d.matched_terms or any(strong_meaning(s, evidence) for s in d.passages):
                backed.append(d)
        ranking.hidden_no_evidence = len(docs) - len(backed)
        docs = backed
    if terms.specific:  # the query names something: only documents that contain all of it
        wanted = set(range(len(terms.specific)))
        named = [d for d in docs if wanted <= set().union(*(s.specific for s in d.passages))]
        ranking.hidden_not_exact = len(docs) - len(named)
        docs = named
    strong = [d for d in docs if d.percent >= min_match_percent]
    ranking.hidden_below_minimum = len(docs) - len(strong)
    floor = float(min_match_percent)
    if strong and relative_cutoff_percent:
        floor = max(floor, strong[0].percent * relative_cutoff_percent / 100)
        best = [d for d in strong if d.percent >= floor]
        ranking.hidden_below_relative = len(strong) - len(best)
        strong = best
    ranking.documents = strong[:top_n]

    wanted_all = frozenset(range(len(terms.specific)))
    for doc in ranking.documents:
        doc.images = [s for s in doc.passages if s.hit.image_id and s.percent >= floor
                      and (not terms.specific or s.specific == wanted_all)][:IMAGES_PER_RESULT]
    return ranking


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
    if hit.image_id:  # "Image: name (location)": the image itself is shown
        return "\n".join(lines[1:] if len(lines) > 1 else lines)
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

def search(query: str, *, index=None, embedder=None, settings_store=None, image_store=None, top_n: int | None = None,
           min_match_percent: int | None = None, relative_cutoff_percent: int | None = None) -> SearchResponse:
    from . import factory

    index = index or factory.get_index()
    embedder = embedder or factory.get_embedder()
    settings_store = settings_store or factory.get_settings_store()
    values = settings_store.effective()
    top_n = values["top_n"] if top_n is None else top_n
    minimum = values["min_match_percent"] if min_match_percent is None else min_match_percent
    relative = values["relative_cutoff_percent"] if relative_cutoff_percent is None else relative_cutoff_percent

    query = " ".join(query.split())[:MAX_QUERY_CHARS]
    response = SearchResponse(query=query, top_n=top_n, min_match_percent=minimum, relative_cutoff_percent=relative)
    if not query:
        return response
    started = time.perf_counter()
    vector = embedder.embed_query(query)
    hits = index.search(query, vector, top=settings_store.candidates)
    related = SynonymMap(settings_store.synonyms)
    ranking = rank_documents(hits, top_n, minimum, relative, query, settings_store.evidence, related)
    for rank, doc in enumerate(ranking.documents, start=1):
        hit = doc.best.hit
        response.results.append(ResultDocument(
            rank=rank, doc_id=hit.doc_id, file_name=hit.file_name, file_type=hit.file_type, location=hit.location,
            uploaded_at=hit.uploaded_at, passage_id=hit.id, match_percent=doc.percent, score_source=doc.best.source,
            snippet=build_snippet(snippet_source(hit), query, related, keep_lines=hit.file_type == "xlsx"),
            reranker_score=hit.reranker_score, cosine=hit.cosine, exact_match=doc.best.exact,
            matched_terms=doc.matched_terms,
            images=_result_images(doc, image_store),
        ))
    response.passages_considered = len(hits)
    response.documents_considered = ranking.considered
    response.hidden_below_minimum = ranking.hidden_below_minimum
    response.hidden_below_relative = ranking.hidden_below_relative
    response.hidden_not_exact = ranking.hidden_not_exact
    response.hidden_no_evidence = ranking.hidden_no_evidence
    response.elapsed_seconds = time.perf_counter() - started
    return response


def _result_images(doc: RankedDocument, image_store=None) -> list[ResultImage]:
    """The matching images of one result, with their metadata from the document's image manifest."""
    if not doc.images:
        return []
    from . import factory

    try:
        records = {r.get("imageId"): r for r in (image_store or factory.get_image_store()).manifest(doc.best.hit.doc_id)}
    except Exception:  # noqa: BLE001 - the text result is still useful without its images
        log.warning("Could not read the image list of %s", doc.best.hit.file_name, exc_info=True)
        return []
    out = []
    for scored in doc.images:
        record = records.get(scored.hit.image_id)
        if record is None:  # re-indexed or deleted since the search index was written
            continue
        out.append(ResultImage(
            image_id=record["imageId"], doc_id=doc.best.hit.doc_id, location=record.get("location") or "",
            page=record.get("page"), caption=record.get("caption") or "", alt_text=record.get("altText") or "",
            original_name=record.get("originalName") or "", width=int(record.get("width") or 0),
            height=int(record.get("height") or 0), format=record.get("format") or "", match_percent=scored.percent))
    return out
