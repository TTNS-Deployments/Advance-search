import pytest

from advancesearch.embeddings import MockEmbeddings, SynonymMap
from advancesearch.index import Hit, LocalIndex
from advancesearch.search import analyse_query, build_snippet, contains, match_score, rank_documents


def hit(doc, chunk=0, reranker=None, cosine=None, score=0.0, content="text", image_id="", name=None):
    return Hit(id=f"{doc}-{chunk}", doc_id=doc, file_name=name or f"{doc}.pdf", file_type="pdf", location="Page 1",
               chunk_index=chunk, uploaded_at="2026-01-01T00:00:00Z", content=content, score=score,
               reranker_score=reranker, cosine=cosine, image_id=image_id)


def kept(ranking):
    return [d.best.hit.doc_id for d in ranking.documents]


@pytest.mark.parametrize("reranker,expected", [(4.0, 100), (3.0, 75), (2.02, 50), (0.0, 0), (4.6, 100), (-1, 0)])
def test_match_from_reranker(reranker, expected):
    assert match_score(hit("a", reranker=reranker, cosine=0.1)) == (expected, "semantic")


@pytest.mark.parametrize("cosine,expected", [(0.834, 83), (1.2, 100), (-0.3, 0), (None, 0)])
def test_match_falls_back_to_cosine(cosine, expected):
    assert match_score(hit("a", reranker=None, cosine=cosine)) == (expected, "vector")


def test_groups_by_document_using_best_chunk():
    hits = [hit("a", 0, reranker=1.0), hit("a", 1, reranker=3.0), hit("b", 0, reranker=2.0), hit("b", 1, reranker=0.5)]
    ranking = rank_documents(hits, 10, 0)
    assert [(d.best.hit.doc_id, d.best.hit.chunk_index, d.percent) for d in ranking.documents] == [("a", 1, 75),
                                                                                                   ("b", 0, 50)]
    assert ranking.considered == 2  # one result per document, never the same document twice


def test_top_n_and_minimum():
    hits = [hit(d, reranker=r) for d, r in [("a", 3.6), ("b", 3.0), ("c", 2.0), ("d", 1.0), ("e", 0.6), ("f", 0.2)]]
    ranking = rank_documents(hits, top_n=3, min_match_percent=20)
    assert kept(ranking) == ["a", "b", "c"]
    assert ranking.considered == 6 and ranking.hidden_below_minimum == 2  # e (15%) and f (5%) are below 20%
    ranking = rank_documents(hits, top_n=10, min_match_percent=20)
    assert kept(ranking) == ["a", "b", "c", "d"]
    assert ranking.hidden_below_minimum == 2


def test_nothing_above_minimum():
    ranking = rank_documents([hit("a", reranker=0.1)], top_n=3, min_match_percent=20)
    assert ranking.documents == [] and ranking.considered == 1 and ranking.hidden_below_minimum == 1


def test_mixed_sources_per_document():
    ranking = rank_documents([hit("a", reranker=3.2), hit("b", cosine=0.9)], 3, 0)
    assert [(d.best.hit.doc_id, d.percent, d.best.source) for d in ranking.documents] == [("b", 90, "vector"),
                                                                                           ("a", 80, "semantic")]


def test_relative_cutoff_drops_documents_far_below_the_best():
    hits = [hit(d, reranker=r) for d, r in [("a", 3.2), ("b", 2.0), ("c", 1.8), ("d", 1.6)]]  # 80, 50, 45, 40 %
    ranking = rank_documents(hits, top_n=10, min_match_percent=30, relative_cutoff_percent=60)
    assert kept(ranking) == ["a", "b"]  # 60% of 80 = 48
    assert ranking.hidden_below_relative == 2 and ranking.hidden_below_minimum == 0
    assert kept(rank_documents(hits, 10, 30, 0)) == ["a", "b", "c", "d"]  # 0 turns the relative cutoff off


def test_exact_phrase_outranks_loose_meaning():
    hits = [hit("loose", reranker=2.8, content="Diagrams of the overall system and how parts connect."),
            hit("exact", reranker=2.6, content="Figure 3 shows the architecture diagram of the platform.")]
    ranking = rank_documents(hits, 10, 0, 0, query="the architecture diagram")
    assert kept(ranking) == ["exact", "loose"]
    assert ranking.documents[0].best.exact and ranking.documents[0].percent == 65 + 10
    assert not ranking.documents[1].best.exact


def test_specific_term_keeps_only_documents_that_contain_it():
    hits = [hit("tablet", reranker=3.0, content="The FT-200 battery lasts 14 hours."),
            hit("meter", reranker=3.2, content="The SM-3 meter battery lasts ten years.")]
    assert kept(rank_documents(hits, 10, 0, 0, query="FT200 battery")) == ["tablet"]
    ranking = rank_documents(hits, 10, 0, 0, query="XR-900 battery")  # named, but in no document
    assert ranking.documents == [] and ranking.hidden_not_exact == 2


def test_file_name_query_matches_the_file():
    hits = [hit("a", reranker=1.6, name="Leave-Policy-2026.pdf"), hit("b", reranker=2.4, name="Travel.pdf")]
    assert kept(rank_documents(hits, 10, 0, 0, query="Leave-Policy-2026.pdf")) == ["a"]


def test_matching_images_are_attached_to_their_document():
    hits = [hit("a", 0, reranker=3.0, content="Network overview text."),
            hit("a", 1, reranker=3.2, content="Image: network-diagram.png (Page 2)\nFigure 2: network diagram",
                image_id="1" * 16),
            hit("a", 2, reranker=0.8, content="Image: logo.png (Page 1)", image_id="2" * 16)]
    ranking = rank_documents(hits, 3, 30, 60, query="network diagram")
    assert len(ranking.documents) == 1
    assert [s.hit.image_id for s in ranking.documents[0].images] == ["1" * 16]  # the weak image is left out


def test_query_analysis():
    terms = analyse_query('show "figure 3" of SM-3 in wiring-diagram.png please')
    assert ("figure", "3") in terms.specific and ("sm", "3") in terms.specific
    assert ("wiring", "diagram", "png") in terms.specific
    assert analyse_query("how many days off do I get").specific == ()
    assert analyse_query("<img src=x onerror=alert(1)> annual leave").specific == ()  # markup is not a code
    assert analyse_query("what is the architecture diagram").phrase == ("architecture", "diagram")
    assert contains(["the", "ft", "200", "tablet"], ("ft200",)) and contains(["ft200"], ("ft", "200"))
    assert not contains(["ft", "2000"], ("ft", "200"))


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
    ranking = rank_documents(hits, 3, 0)
    assert ranking.documents[0].best.source == "vector"
    assert ranking.documents[0].percent == round(hits[0].cosine * 100)


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


# ---------------------------------------------------------------------------- evidence: keyword or strong meaning

def test_unrelated_document_without_keyword_is_hidden_even_at_40_percent():
    """The Azure case: vector search always returns neighbours, and the ranker gives unrelated passages ~1.6/4."""
    from advancesearch.search import Evidence

    hits = [hit("leave", reranker=3.2, content="Annual leave entitlement is 24 working days."),
            hit("meter", reranker=1.6, content="The smart meter sends readings every 15 minutes.")]
    ranking = rank_documents(hits, 3, 20, 0, "how much annual leave", Evidence())
    assert [d.best.hit.doc_id for d in ranking.documents] == ["leave"]
    assert ranking.hidden_no_evidence == 1
    assert ranking.documents[0].matched_terms == ["annual", "leave"]  # as typed, not stemmed


def test_strong_meaning_without_keyword_is_kept():
    from advancesearch.search import Evidence

    hits = [hit("leave", reranker=2.4, content="Every employee receives an annual entitlement of 24 working days.")]
    kept = rank_documents(hits, 3, 20, 0, "how many vacations", Evidence()).documents
    assert [d.best.hit.doc_id for d in kept] == ["leave"] and kept[0].matched_terms == []
    weak = [hit("leave", reranker=1.9, content="Every employee receives an annual entitlement of 24 working days.")]
    assert rank_documents(weak, 3, 20, 0, "how many vacations", Evidence()).documents == []


def test_vector_fallback_uses_cosine_threshold():
    from advancesearch.search import Evidence

    hits = [hit("a", cosine=0.5, content="unrelated words"), hit("b", cosine=0.4, content="other words")]
    kept = rank_documents(hits, 3, 20, 0, "zebra migration", Evidence(cosine=0.45)).documents
    assert [d.best.hit.doc_id for d in kept] == ["a"]


def test_keyword_in_file_name_or_related_term_counts():
    from advancesearch.search import Evidence

    related = SynonymMap([["days off", "leave", "annual entitlement"]])
    hits = [hit("x", reranker=1.2, content="Annual entitlement is 24 working days."),
            hit("y", reranker=1.2, content="Nothing relevant here.")]
    hits[1].file_name = "Pricing-2026.pdf"
    kept = rank_documents(hits, 3, 20, 0, "days off", Evidence(), related).documents
    assert [d.best.hit.doc_id for d in kept] == ["x"]
    kept = rank_documents(hits, 3, 20, 0, "pricing sheet", Evidence(), related).documents
    assert [d.best.hit.doc_id for d in kept] == ["y"]


def test_filler_words_and_stopwords_are_not_evidence():
    from advancesearch.search import Evidence, query_keywords

    assert query_keywords("please find the document about it") == []
    hits = [hit("a", reranker=1.5, content="Find this document for more information about it.")]
    assert rank_documents(hits, 3, 20, 0, "please find the document about pets", Evidence()).documents == []
