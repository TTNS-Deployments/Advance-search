"""Embeddings: Azure OpenAI (managed identity) or a deterministic local mock.

The mock hashes words, word groups from ``mock_synonyms`` in ``Config/search.yaml`` and character trigrams
into a fixed-size vector, so related wording ("days off" and "annual entitlement") lands closer together
than unrelated wording. It is good enough for local development and tests, not a language model.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import re
import time
from collections import Counter
from functools import lru_cache

from .config import Settings

log = logging.getLogger(__name__)

STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further get got had has have having he her here
hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of on
once only or other our ours ourselves out over own same she should so some such than that the their theirs them
themselves then there these they this those through to too under until up very was we were what when where which
while who whom why will with would you your yours yourself yourselves many much also may might must shall us
""".split())

WORD_RE = re.compile(r"[a-z0-9]+")


def stem(word: str) -> str:
    """Tiny suffix stripper so "approves", "approved" and "approving" share a root."""
    for suffix, keep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3 and not word.endswith("ss"):
            return word[: -len(suffix)] + keep
    return word


def words(text: str) -> list[str]:
    return [stem(w) for w in WORD_RE.findall(text.lower())]


class SynonymMap:
    """Maps word sequences (stemmed) to a concept id, longest match first."""

    def __init__(self, groups: list[list[str]]):
        self.phrases: dict[tuple[str, ...], int] = {}
        for gid, group in enumerate(groups):
            for phrase in group:
                key = tuple(words(str(phrase)))
                if key:
                    self.phrases.setdefault(key, gid)
        self.max_len = max((len(k) for k in self.phrases), default=1)

    def concepts(self, tokens: list[str]) -> list[int]:
        found, i = [], 0
        while i < len(tokens):
            for n in range(min(self.max_len, len(tokens) - i), 0, -1):
                gid = self.phrases.get(tuple(tokens[i:i + n]))
                if gid is not None:
                    found.append(gid)
                    i += n - 1
                    break
            i += 1
        return found

    def concept_terms(self, gid: int) -> list[tuple[str, ...]]:
        return [k for k, v in self.phrases.items() if v == gid]


@lru_cache(maxsize=65536)
def _slot(feature: str, dims: int) -> tuple[int, float]:
    digest = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "big")
    return digest % dims, (1.0 if (digest >> 63) & 1 else -1.0)


class MockEmbeddings:
    WORD_WEIGHT = 1.0
    CONCEPT_WEIGHT = 2.2
    TRIGRAM_WEIGHT = 0.25

    def __init__(self, dimensions: int = 1536, synonyms: list[list[str]] | None = None):
        self.dimensions = dimensions
        if synonyms is None:
            from .factory import get_settings_store

            synonyms = get_settings_store().synonyms
        self.synonyms = SynonymMap(synonyms)

    def features(self, text: str) -> Counter:
        tokens = words(text)
        feats: Counter = Counter()
        for gid in self.synonyms.concepts(tokens):
            feats[f"c:{gid}"] += self.CONCEPT_WEIGHT
        for tok in tokens:
            if tok in STOPWORDS or len(tok) < 2:
                continue
            feats[f"w:{tok}"] += self.WORD_WEIGHT
            padded = f"#{tok}#"
            grams = [padded[i:i + 3] for i in range(len(padded) - 2)]
            for gram in grams:
                feats[f"g:{gram}"] += self.TRIGRAM_WEIGHT / len(grams)
        return feats

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dimensions
        for feature, weight in self.features(text).items():
            idx, sign = _slot(feature, self.dimensions)
            vec[idx] += sign * (1.0 + math.log(weight)) if weight >= 1 else sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


class EmbeddingError(RuntimeError):
    pass


class AzureOpenAIEmbeddings:
    """Sends requests to the Azure OpenAI embeddings REST API, with retry and back-off on 429 and 5xx."""

    MAX_ATTEMPTS = 6

    def __init__(self, settings: Settings, session=None, sleep=time.sleep):
        import requests

        if not settings.openai_endpoint:
            raise RuntimeError("Set AZURE_OPENAI_ENDPOINT for EMBEDDING_BACKEND=azure")
        self.settings = settings
        self.dimensions = settings.embedding_dimensions
        self.session = session or requests.Session()
        self.sleep = sleep
        self.url = (f"{settings.openai_endpoint}/openai/deployments/{settings.embedding_deployment}/embeddings"
                    f"?api-version={settings.openai_api_version}")

    def _headers(self) -> dict:
        if self.settings.openai_key:
            return {"api-key": self.settings.openai_key}
        from .azure_auth import bearer_token

        return {"Authorization": f"Bearer {bearer_token()}"}

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        body = {"input": texts}
        # text-embedding-3 models can shorten vectors; older models reject the parameter.
        if "embedding-3" in self.settings.embedding_deployment:
            body["dimensions"] = self.dimensions
        import requests

        last_error = ""
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                response = self.session.post(self.url, json=body, headers=self._headers(), timeout=60)
            except requests.RequestException as exc:
                status, last_error, retry_after = None, f"{exc.__class__.__name__}: {exc}", None
            else:
                status, retry_after = response.status_code, response.headers.get("Retry-After")
                if status == 200:
                    data = sorted(response.json()["data"], key=lambda d: d["index"])
                    vectors = [d["embedding"] for d in data]
                    if vectors and len(vectors[0]) != self.dimensions:
                        raise EmbeddingError(f"The embedding model returned {len(vectors[0])} dimensions, "
                                             f"EMBEDDING_DIMENSIONS is {self.dimensions}")
                    return vectors
                last_error = f"HTTP {status}: {response.text[:300]}"
                if status not in (408, 429) and status < 500:
                    raise EmbeddingError(f"Embeddings request failed: {last_error}")
            if attempt == self.MAX_ATTEMPTS:
                break
            try:
                delay = float(retry_after) if retry_after else 0.0
            except ValueError:
                delay = 0.0
            delay = min(60.0, delay or (2 ** attempt) + random.uniform(0, 1))
            log.warning("Embeddings call failed (%s), retry %s in %.1fs", last_error, attempt, delay)
            self.sleep(delay)
        raise EmbeddingError(f"Embeddings request failed after {self.MAX_ATTEMPTS} attempts: {last_error}")

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
