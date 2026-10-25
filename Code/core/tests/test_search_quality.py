"""Local hybrid search against Data/sample_docs/queries.yaml: the expected document must be in the top 3."""
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
              f"({report['accuracy']:.0%}); rank 1: {ranks.count(1)}, rank 2: {ranks.count(2)}, rank 3: {ranks.count(3)}")
    assert not misses, misses
    assert len(load_queries()) >= 15
    kinds = {q["kind"] for q in load_queries()}
    assert kinds == {"keyword", "paraphrase", "excel"}


def test_unrelated_query_shows_no_close_match(seeded):
    from advancesearch.search import search

    response = search("football world cup results")
    assert response.results == []
    assert response.hidden_below_minimum > 0


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
