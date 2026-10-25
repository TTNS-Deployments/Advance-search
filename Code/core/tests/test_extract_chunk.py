import re

import pytest
from helpers import make_blank_pdf, make_docx, make_pdf, make_xlsx

from advancesearch.chunk import ChunkOptions, chunk_rows, chunk_text, count_tokens
from advancesearch.extract import ExtractionError, extract_passages, file_type_for

# ---------------------------------------------------------------------------- extraction


def test_file_types():
    assert file_type_for("a.PDF") == "pdf"
    assert file_type_for("b.docx") == "docx"
    assert file_type_for("c.xlsx") == "xlsx"
    assert file_type_for("d.doc") is None
    assert file_type_for("e.txt") is None


def test_pdf_passages_carry_page_numbers(tmp_path):
    path = make_pdf(tmp_path / "p.pdf", ["Annual entitlement is 24 working days.", "Sick leave is 12 days."])
    passages = list(extract_passages(path, "pdf"))
    assert [p.location for p in passages] == ["Page 1", "Page 2"]
    assert "Annual entitlement" in passages[0].text
    assert "Sick leave" in passages[1].text


def test_pdf_without_text_yields_nothing(tmp_path):
    assert list(extract_passages(make_blank_pdf(tmp_path / "scan.pdf"), "pdf")) == []


def test_corrupt_pdf_raises(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not really a pdf")
    with pytest.raises(ExtractionError):
        list(extract_passages(path, "pdf"))


def test_docx_keeps_heading_context_and_tables(tmp_path):
    path = make_docx(tmp_path / "d.docx", [
        ("h1", "Security"), ("p", "Intro text."),
        ("h2", "Lost devices"), ("p", "Report a lost laptop within one hour."),
        ("table", [["Class", "Handling"], ["Restricted", "Encrypted"]]),
    ])
    passages = list(extract_passages(path, "docx"))
    assert [p.location for p in passages] == ["Section: Security", "Section: Lost devices"]
    lost = passages[1].text
    assert lost.startswith("Security > Lost devices")  # heading path repeated in the passage
    assert "Report a lost laptop" in lost
    assert "Restricted | Encrypted" in lost


def test_docx_without_headings(tmp_path):
    passages = list(extract_passages(make_docx(tmp_path / "d.docx", [("p", "Just text.")]), "docx"))
    assert passages[0].location == "Document"


def test_empty_docx_yields_nothing(tmp_path):
    assert list(extract_passages(make_docx(tmp_path / "e.docx", []), "docx")) == []


def test_xlsx_repeats_header_in_every_passage_and_skips_empty_and_hidden(tmp_path):
    rows = [["Item", "Price (INR)", "Unit"]]
    rows += [[f"Item number {i} with a longer description to fill tokens", i * 10.0, "Each"] for i in range(1, 121)]
    rows.insert(5, [None, None, None])  # empty row
    path = make_xlsx(tmp_path / "x.xlsx", {"Prices": rows, "Secret": [["Note"], ["hidden content"]]}, hidden=("Secret",))
    passages = list(extract_passages(path, "xlsx", ChunkOptions(target_tokens=200, max_tokens=250)))
    assert len(passages) > 2
    for p in passages:
        assert p.text.startswith("Sheet: Prices\nColumns: Item | Price (INR) | Unit")
        assert re.fullmatch(r"Sheet 'Prices', rows \d+-\d+", p.location)
    text = "\n".join(p.text for p in passages)
    assert "hidden content" not in text
    assert "Item number 1 with a longer description to fill tokens | 10 | Each" in text  # 10.0 shown as 10
    # Row numbers are the spreadsheet's own (the empty row 6 is skipped, not renumbered)
    assert passages[0].location.startswith("Sheet 'Prices', rows 2-")


def test_xlsx_hidden_sheets_can_be_included(tmp_path):
    path = make_xlsx(tmp_path / "x.xlsx", {"A": [["H"], ["v"]], "B": [["Note"], ["hidden content"]]}, hidden=("B",))
    text = " ".join(p.text for p in extract_passages(path, "xlsx", excel={"skip_hidden_sheets": False}))
    assert "hidden content" in text


def test_empty_xlsx_yields_nothing(tmp_path):
    assert list(extract_passages(make_xlsx(tmp_path / "e.xlsx", {"Empty": []}), "xlsx")) == []


# ---------------------------------------------------------------------------- chunking

WORDS = ("alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa "
         "quebec romeo sierra tango uniform victor whiskey xray yankee zulu").split()


def _text(sentences=200, words=12):
    return " ".join(" ".join(WORDS[(i + j) % len(WORDS)] for j in range(words)).capitalize() + "." for i in range(sentences))


def test_chunks_respect_size_limits():
    opts = ChunkOptions(target_tokens=500, max_tokens=600, overlap_ratio=0.15, max_chars=4000)
    chunks = chunk_text(_text(), opts)
    assert len(chunks) > 3
    for c in chunks:
        assert count_tokens(c) <= 600
        assert len(c) <= 4000
    assert all(count_tokens(c) >= 300 for c in chunks[:-1])  # no tiny passages in the middle


def test_chunks_overlap_about_15_percent():
    opts = ChunkOptions(target_tokens=200, max_tokens=260, overlap_ratio=0.15)
    text = " ".join(f"Sentence number {i} talks about topic {i}." for i in range(200))
    chunks = chunk_text(text, opts)
    for a, b in zip(chunks, chunks[1:]):
        first_sentence_of_b = b.split(".")[0] + "."
        assert first_sentence_of_b in a  # the next passage starts inside the previous one
        overlap = a[a.index(first_sentence_of_b):]
        assert 0 < count_tokens(overlap) <= 0.15 * 200 + 10


def test_never_cuts_mid_word():
    long_sentence = " ".join(["supercalifragilistic"] * 900)  # one sentence far beyond max_tokens
    vocabulary = {"supercalifragilistic"}
    for c in chunk_text(long_sentence, ChunkOptions(target_tokens=100, max_tokens=120)):
        assert set(c.split()) <= vocabulary
        assert count_tokens(c) <= 120


def test_splits_on_paragraphs_and_sentences():
    text = "First paragraph one. First paragraph two.\n\nSecond paragraph."
    assert chunk_text(text) == ["First paragraph one. First paragraph two.\n\nSecond paragraph."]


def test_prefix_repeated_in_every_chunk():
    chunks = chunk_text(_text(80), ChunkOptions(target_tokens=150, max_tokens=200), prefix="Guide > Section")
    assert len(chunks) > 1
    assert all(c.startswith("Guide > Section\n") for c in chunks)
    assert all(count_tokens(c) <= 200 for c in chunks)


def test_empty_text_gives_no_chunks():
    assert chunk_text("   \n\n  ") == []


def test_chunk_rows_groups_without_splitting_rows():
    rows = [(i, f"row {i} " + "word " * 20) for i in range(2, 60)]
    groups = chunk_rows(rows, ChunkOptions(target_tokens=120), prefix="Columns: A | B")
    assert groups[0][0] == 2 and groups[-1][1] == 59
    covered = [n for first, last, _ in groups for n in range(first, last + 1)]
    assert covered == list(range(2, 60))  # every row exactly once, in order
    assert all(text.startswith("Columns: A | B\n") for _, _, text in groups)
