"""Local hybrid search against Data/sample_docs/queries.yaml: the expected document must be shown, unrelated
queries must show nothing, and image queries must return the image."""
import pytest

from advancesearch import cli
from advancesearch.evaluation import evaluate, load_queries


@pytest.fixture
def seeded(monkeypatch, capsys):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")  # the real default
    from advancesearch.config import reset_settings_cache

    reset_settings_cache()
    assert cli.main(["seed"]) == 0
    return capsys.readouterr().out


def test_seed_indexes_every_sample_document(seeded):
    assert "Seeding 13 sample documents" in seeded
    assert seeded.count(": indexed") == 12
    assert "Scanned-Delivery-Note.pdf: no_text" in seeded  # the scan sample has no text layer


def test_sample_queries_find_expected_document_in_top_3(seeded, capsys):
    report = evaluate()
    misses = [r for r in report["rows"] if not r["hit"]]
    with capsys.disabled():
        ranks = [r["rank"] for r in report["rows"]]
        print(f"\nTop-3 accuracy on {report['total']} sample queries: {report['hits']}/{report['total']} "
              f"({report['accuracy']:.0%}); rank 1: {ranks.count(1)}, rank 2: {ranks.count(2)}, rank 3: {ranks.count(3)}; "
              f"precision {report['hits']}/{report['shown']} ({report['precision']:.0%})")
    assert not misses, misses
    assert len(load_queries()) >= 15
    kinds = {q["kind"] for q in load_queries()}
    assert kinds == {"keyword", "paraphrase", "excel"}


def test_unrelated_query_shows_no_close_match(seeded):
    from advancesearch.search import search

    response = search("football world cup results")
    assert response.results == []
    assert response.hidden_no_evidence > 0  # no shared keyword and no strong meaning match
    assert response.to_dict()["message"] == "No matching documents found."


def test_unrelated_queries_return_nothing(seeded):
    report = evaluate()
    assert len(report["unrelated"]) >= 4
    assert all(r["ok"] for r in report["unrelated"]), report["unrelated"]


def test_specific_queries_return_only_the_relevant_document(seeded):
    """(b) Precision: weaker documents are hidden, not just ranked lower; most queries show exactly one."""
    from advancesearch.search import search

    for query, expected in [("how many days off do I get", "Leave-Policy-2026.pdf"),
                            ("what to do if my laptop is stolen", "Information-Security-Policy.docx"),
                            ("hotel limit per night in metro cities", "Travel-and-Expense-Policy.pdf"),
                            ("when does the migration go live", "Cloud-Migration-Project-Plan.xlsx"),
                            ("can I work from home on Fridays", "Hybrid-Working-Guidelines.docx"),
                            ("Leave-Policy-2026.pdf", "Leave-Policy-2026.pdf"),
                            ("SM-3 tamper", "SM-3-Smart-Meter-Datasheet.docx")]:
        response = search(query)
        assert [r.file_name for r in response.results] == [expected], query
        assert response.hidden > 0
    report = evaluate()
    assert report["precision"] >= 0.7, report["precision"]
    for row in report["rows"]:  # the expected document is the best one shown, nothing is listed twice
        assert len(set(row["got"])) == len(row["got"])
    scores = [r.match_percent for r in search("battery life of the field tablet").results]
    assert scores == sorted(scores, reverse=True)
    assert all(s >= 30 and s >= scores[0] * 0.6 for s in scores)


def test_image_queries_return_the_image(seeded):
    """(a) Image names, captions and topics return the image itself with its document and location."""
    report = evaluate()
    assert len(report["images"]) >= 5
    assert all(r["ok"] for r in report["images"]), [r for r in report["images"] if not r["ok"]]
    from advancesearch import factory
    from advancesearch.search import search

    [result] = search("sm3-wiring-diagram.png").results
    [image] = result.images
    assert result.file_name == "SM-3-Smart-Meter-Datasheet.docx" and image.original_name == "sm3-wiring-diagram.png"
    assert image.alt_text.startswith("Wiring diagram of the SM-3") and image.location == "Section: Overview"
    assert b"".join(factory.get_image_store().iter_bytes(factory.get_image_store().get(image.doc_id, image.image_id)))
    figures = {r.file_name for r in search("figure 1").results}
    assert figures == {"SM-3-Smart-Meter-Datasheet.docx", "FT-200-Field-Tablet-Specification.pdf",
                       "Cloud-Migration-Project-Plan.xlsx"}


def test_sample_images_are_extracted_and_logos_skipped(seeded):
    from advancesearch.ingest import get_document_service

    images = {d.name: d.images for d in get_document_service().list()}
    assert images["FT-200-Field-Tablet-Specification.pdf"] == 1  # the figure, not the 40 x 40 logo on each page
    assert images["SM-3-Smart-Meter-Datasheet.docx"] == 1 and images["Cloud-Migration-Project-Plan.xlsx"] == 1
    assert sum(images.values()) == 3


def test_paraphrase_shares_no_keywords_with_document(seeded):
    from advancesearch.search import search

    top = search("how many days off do I get").results[0]
    assert top.file_name == "Leave-Policy-2026.pdf"
    from pathlib import Path

    from pypdf import PdfReader

    text = " ".join(p.extract_text() for p in PdfReader(str(Path(cli.get_settings().data_dir) / "sample_docs" /
                                                          "Leave-Policy-2026.pdf")).pages).lower()
    assert "days off" not in text and "annual entitlement" in text


def test_cli_search_and_status(seeded, capsys):
    assert cli.main(["search", "who approves a purchase over five lakh"]) == 0
    out = capsys.readouterr().out
    assert "1. Procurement-Approval-Matrix.xlsx" in out and "(semantic)" in out and "Sheet 'Approval limits'" in out
    assert cli.main(["status"]) == 0
    assert "13 documents" in capsys.readouterr().out
    assert cli.main(["reset"]) == 1  # needs --yes
    assert cli.main(["reset", "--yes"]) == 0
    assert cli.main(["status"]) == 0
    assert "0 documents" in capsys.readouterr().out
