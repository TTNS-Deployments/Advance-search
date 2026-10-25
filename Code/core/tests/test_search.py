import pytest

from advancesearch.embeddings import MockEmbeddings, SynonymMap
from advancesearch.index import Hit, LocalIndex
from advancesearch.search import build_snippet, group_by_document, match_score, rank_documents


def hit(doc, chunk=0, reranker=None, cosine=None, score=0.0, content="text"):
    return Hit(id=f"{doc}-{chunk}", doc_id=doc, file_name=f"{doc}.pdf", file_type="pdf", location="Page 1",
               chunk_index=chunk, uploaded_at="2026-01-01T00:00:00Z", content=content, score=score,
               reranker_score=reranker, cosine=cosine)


@pytest.mark.parametrize("reranker,expected", [(4.0, 100), (3.0, 75), (2.02, 50), (0.0, 0), (4.6, 100), (-1, 0)])
def test_match_from_reranker(reranker, expected):
    assert match_score(hit("a", reranker=reranker, cosine=0.1)) == (expected, "semantic")


@pytest.mark.parametrize("cosine,expected", [(0.834, 83), (1.2, 100), (-0.3, 0), (None, 0)])
def test_match_falls_back_to_cosine(cosine, expected):
    assert match_score(hit("a", reranker=None, cosine=cosine)) == (expected, "vector")


def test_groups_by_document_using_best_chunk():
    hits = [hit("a", 0, reranker=1.0), hit("a", 1, reranker=3.0), hit("b", 0, reranker=2.0), hit("b", 1, reranker=0.5)]
    grouped = group_by_document(hits)
    assert [(h.doc_id, h.chunk_index, p) for h, p, _ in grouped] == [("a", 1, 75), ("b", 0, 50)]


def test_top_n_and_minimum():
    hits = [hit(d, reranker=r) for d, r in [("a", 3.6), ("b", 3.0), ("c", 2.0), ("d", 1.0), ("e", 0.6), ("f", 0.2)]]
    kept, considered, hidden = rank_documents(hits, top_n=3, min_match_percent=20)
    assert [h.doc_id for h, _, _ in kept] == ["a", "b", "c"]
    assert considered == 6 and hidden == 2  # e (15%) and f (5%) are below 20%
    kept, _, hidden = rank_documents(hits, top_n=10, min_match_percent=20)
    assert [h.doc_id for h, _, _ in kept] == ["a", "b", "c", "d"]
    assert hidden == 2


def test_nothing_above_minimum():
    kept, considered, hidden = rank_documents([hit("a", reranker=0.1)], top_n=3, min_match_percent=20)
    assert kept == [] and considered == 1 and hidden == 1


def test_mixed_sources_per_document():
    kept, _, _ = rank_documents([hit("a", reranker=3.2), hit("b", cosine=0.9)], 3, 0)
    assert [(h.doc_id, p, s) for h, p, s in kept] == [("b", 90, "vector"), ("a", 80, "semantic")]


def test_snippet_highlights_query_and_related_terms():
    related = SynonymMap([["days off", "leave", "annual entitlement"]])
    content = ("This policy explains things. " * 10 + "Every employee receives an annual entitlement of 24 working "
               "days of earned leave per year. " + "Other text follows here. " * 10)
    segments = build_snippet(content, "how many days off do I get", related)
    marked = [t for t, h in segments if h]
    assert "annual entitlement" in marked
    assert "leave" in marked and "days" in marked
    text = "".join(t for t, _ in segments)
    assert text.startswith("… ") and text.endswith(" …")
    assert len(text.split()) <= 52


def test_snippet_escaping_is_left_to_the_template():
    segments = build_snippet("<script>alert(1)</script> leave", "leave")
    assert "".join(t for t, _ in segments).startswith("<script>")  # raw text; templates escape it


def test_local_hybrid_search_without_semantic_uses_vector_score(tmp_path):
    emb = MockEmbeddings(128, [["days off", "leave"]])
    idx = LocalIndex(tmp_path / "i.sqlite3", 128, semantic=False)
    docs = [("a", "Annual leave is 24 working days."), ("b", "The tablet battery lasts 14 hours.")]
    idx.upload([{"id": f"{d}-0", "docId": d, "fileName": f"{d}.pdf", "fileType": "pdf", "location": "Page 1",
                 "chunkIndex": 0, "uploadedAt": "2026-01-01T00:00:00Z", "content": t,
                 "contentVector": emb.embed_query(t)} for d, t in docs])
    hits = idx.search("days off", emb.embed_query("days off"), 50)
    assert hits[0].doc_id == "a"
    assert all(h.reranker_score is None for h in hits)
    kept, _, _ = rank_documents(hits, 3, 0)
    assert kept[0][2] == "vector" and kept[0][1] == round(hits[0].cosine * 100)


def test_search_end_to_end_respects_settings(service, tmp_path):
    from helpers import make_pdf, upload

    from advancesearch import factory
    from advancesearch.search import search

    for i, text in enumerate(["Annual leave entitlement is 24 days.", "Battery runtime is 14 hours.",
                              "Hotel limit per night is INR 7,500.", "Invoices are kept for eight years."]):
        upload(service, make_pdf(tmp_path / f"doc{i}.pdf", [text]))
    response = search("annual leave entitlement")
    assert response.results[0].file_name == "doc0.pdf"
    assert response.results[0].score_source == "semantic"
    assert 0 <= response.results[0].match_percent <= 100
    assert len(response.results) <= 3
    factory.get_settings_store().save({"top_n": 1, "min_match_percent": 0})
    assert len(search("annual leave entitlement").results) == 1
    factory.get_settings_store().save({"top_n": 3, "min_match_percent": 100})
    response = search("annual leave entitlement")
    assert response.results == [] and response.hidden_below_minimum >= 1
    assert search("   ").results == []
