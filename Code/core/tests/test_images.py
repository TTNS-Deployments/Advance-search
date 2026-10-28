"""Image extraction (PDF, Word, Excel), filtering, de-duplication, storage and image search."""
import json

import pytest
from helpers import make_docx_with_image, make_pdf, make_pdf_with_images, make_xlsx_with_image, png, upload

from advancesearch import factory
from advancesearch.images import ImageOptions, extract_images, meaningful_name
from advancesearch.search import search

DIAGRAM = png(400, 220, "#2f4a8a", "Gateway")


# ---------------------------------------------------------------------------- extraction

def test_pdf_image_with_caption_and_nearby_text(tmp_path):
    path = make_pdf_with_images(tmp_path / "design.pdf", [
        (["Text on page one only."], []),
        (["System overview", "Meters send readings to the gateway every 15 minutes.", "", "", "", "", "", "", "",
          "", "", "", "Figure 3: System architecture diagram", "The gateway forwards data to the cloud."],
         [(DIAGRAM, 50, 590, 300, 160)]),
    ])
    images = extract_images(path, "pdf")
    assert len(images) == 1
    image = images[0]
    assert (image.page, image.location, image.width, image.height, image.format) == (2, "Page 2", 400, 220, "png")
    assert image.caption == "Figure 3: System architecture diagram"
    assert "Meters send readings to the gateway" in image.nearby  # above the image
    assert "forwards data to the cloud" in image.nearby          # below the image
    assert "Text on page one" not in image.nearby
    assert len(image.image_id) == 16 and image.image_id == extract_images(path, "pdf")[0].image_id  # stable id
    text = image.search_text(source="design.pdf")
    assert text.startswith("Image (Page 2 of design.pdf)") and "Figure 3: System architecture diagram" in text


def test_small_thin_repeated_and_duplicate_images_are_skipped(tmp_path):
    logo, rule, photo = png(40, 40, "#c0392b"), png(600, 20, "#333333"), png(300, 200, "#13906a", "Photo")
    pages = [([f"Page {n} text"], [(logo, 500, 780, 40, 40), (rule, 50, 700, 500, 16)]) for n in range(1, 4)]
    pages[0][1].append((photo, 50, 400, 300, 200))
    pages[2][1].append((photo, 50, 400, 300, 200))           # the same photo again on page 3
    pages[1][1].append((png(300, 200, "#8e44ad"), 50, 400, 30, 20))  # big pixels, drawn as an icon
    images = extract_images(make_pdf_with_images(tmp_path / "many.pdf", pages), "pdf")
    assert [(i.width, i.height, i.page, i.occurrences) for i in images] == [(300, 200, 1, 2)]


def test_repeated_logo_is_skipped_but_can_be_kept(tmp_path):
    logo = png(120, 120, "#c0392b", "Logo")
    path = make_pdf_with_images(tmp_path / "logo.pdf", [([f"Page {n}"], [(logo, 400, 700, 80, 80)]) for n in range(3)])
    assert extract_images(path, "pdf") == []                                       # on 3 pages: a logo
    assert len(extract_images(path, "pdf", ImageOptions(repeated_pages=0))) == 1


def test_docx_image_alt_text_name_and_caption(tmp_path):
    path = make_docx_with_image(tmp_path / "net.docx", "The core switch links both floors.", DIAGRAM,
                                "network-topology.png", "Topology of the office network", "Figure 2: Network topology",
                                "Each floor has its own access switch.")
    [image] = extract_images(path, "docx")
    assert image.location == "Section: Network design" and image.page is None
    assert (image.original_name, image.alt_text) == ("network-topology.png", "Topology of the office network")
    assert image.caption == "Figure 2: Network topology"
    assert "core switch links both floors" in image.nearby and "access switch" in image.nearby
    assert image.search_text().startswith("Image: network-topology.png (Section: Network design)")


def test_xlsx_image_with_nearby_rows(tmp_path):
    path = make_xlsx_with_image(tmp_path / "plan.xlsx", [["Phase", "Owner"], ["Figure 1: Rollout timeline chart", ""],
                                                         ["Pilot", "Arjun"]], DIAGRAM, "A4")
    [image] = extract_images(path, "xlsx")
    assert image.location == "Sheet 'Plan', cell A4"
    assert image.caption == "Figure 1: Rollout timeline chart"
    assert "Pilot | Arjun" in image.nearby


def test_extraction_can_be_turned_off_and_never_raises(tmp_path):
    path = make_pdf_with_images(tmp_path / "a.pdf", [(["x"], [(DIAGRAM, 50, 500, 300, 160)])])
    assert extract_images(path, "pdf", ImageOptions(enabled=False)) == []
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"PK\x03\x04 not really a zip")
    assert extract_images(broken, "docx") == []


def test_generic_names_are_not_used_as_text():
    assert not meaningful_name("Im1.png") and not meaningful_name("image12.jpeg") and not meaningful_name("Picture 3")
    assert not meaningful_name("FormXob.11f4d409aaefa0977a82076afada410b.png")
    assert meaningful_name("network-topology.png") and meaningful_name("FT-200 front.jpg")


# ---------------------------------------------------------------------------- ingestion and storage

def architecture_pdf(tmp_path):
    return make_pdf_with_images(tmp_path / "Platform-Design.pdf", [
        (["Platform design", "This document describes the metering platform.", "", "", "", "", "", "", "", "", "",
          "", "Figure 3: System architecture diagram", "Gateways forward meter data to the cloud."],
         [(DIAGRAM, 50, 590, 300, 160)]),
    ])


def test_ingestion_saves_images_and_metadata(service, tmp_path):
    result = upload(service, architecture_pdf(tmp_path))
    doc = service.get(result.name)
    assert doc.status == "indexed" and doc.images == 1
    [record] = factory.get_image_store().manifest(result.doc_id)
    assert record["docId"] == result.doc_id and record["fileName"] == "Platform-Design.pdf"
    assert (record["page"], record["width"], record["height"], record["format"]) == (1, 400, 220, "png")
    assert record["path"] == f"extracted-images/{result.doc_id}/{record['imageId']}.png"
    assert record["caption"] == "Figure 3: System architecture diagram"
    data = b"".join(factory.get_image_store().iter_bytes(record))
    assert data.startswith(b"\x89PNG") and len(data) == record["bytes"]

    removed = service.delete(result.name)
    assert removed == doc.chunks
    assert factory.get_image_store().manifest(result.doc_id) == []
    assert factory.get_blob_store().list("extracted-images", prefix=f"{result.doc_id}/") == []


def test_image_name_search_returns_the_image(service, tmp_path):
    upload(service, make_docx_with_image(tmp_path / "Network-Guide.docx", "The core switch links both floors.",
                                         DIAGRAM, "network-topology.png", "Topology of the office network",
                                         "Figure 2: Network topology", "Each floor has its own access switch."))
    upload(service, make_pdf(tmp_path / "Leave.pdf", ["Annual leave entitlement is 24 days."]))
    for query in ("network-topology.png", "network topology diagram", "figure 2"):
        response = search(query)
        assert [r.file_name for r in response.results] == ["Network-Guide.docx"], query
        [image] = response.results[0].images
        assert image.original_name == "network-topology.png" and image.caption == "Figure 2: Network topology"
        assert image.location == "Section: Network design" and image.match_percent >= 30
    assert search("annual leave entitlement").results[0].images == []  # no image for a text-only match
    body = search("network-topology.png").to_dict()
    assert body["results"][0]["images"][0]["imageId"] == image.image_id


def test_reindex_extracts_images_of_documents_indexed_before(service, tmp_path):
    """A document indexed by the earlier version (no "images" in its metadata) is processed again."""
    result = upload(service, architecture_pdf(tmp_path))
    blobs = factory.get_blob_store()
    meta = {k: v for k, v in blobs.info("documents", result.name).metadata.items() if k != "images"}
    blobs.set_metadata("documents", result.name, meta)
    factory.get_image_store().delete_document(result.doc_id)
    assert service.pending(include_finished=False) == []          # the periodic scan leaves it alone
    assert service.pending(include_finished=True) == [result.name]  # start-up scan and Sync pick it up
    assert service.process(result.name) == "indexed"
    assert service.get(result.name).images == 1
    assert service.pending(include_finished=True) == []
    assert service.process(result.name) is None  # indexed and up to date: not claimed again


def test_cli_reindex_keep_index(service, tmp_path, capsys):
    from advancesearch import cli

    upload(service, architecture_pdf(tmp_path))
    assert cli.main(["reindex", "--keep-index"]) == 0
    out = capsys.readouterr().out
    assert "Processing 1 documents again" in out and "Platform-Design.pdf: indexed" in out and "1 images" in out
    assert cli.main(["search", "architecture diagram"]) == 0
    out = capsys.readouterr().out
    assert "1. Platform-Design.pdf" in out and "image " in out and "Figure 3: System architecture diagram" in out


def test_local_index_from_before_images_is_migrated(tmp_path):
    import sqlite3

    from advancesearch.index import LocalIndex

    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO meta VALUES ('dimensions', '4');
        CREATE TABLE chunks (id TEXT PRIMARY KEY, docId TEXT, fileName TEXT, fileType TEXT, location TEXT,
            chunkIndex INTEGER, uploadedAt TEXT, content TEXT, vector BLOB);
    """)
    conn.close()
    index = LocalIndex(path, 4)
    index.upload([{"id": "d-0", "docId": "d", "fileName": "d.pdf", "fileType": "pdf", "location": "Page 1",
                   "chunkIndex": 0, "uploadedAt": "2026-01-01T00:00:00Z", "content": "gateway diagram",
                   "contentVector": [1.0, 0.0, 0.0, 0.0], "imageId": "a" * 16}])
    [hit] = index.search("gateway diagram", [1.0, 0.0, 0.0, 0.0])
    assert hit.image_id == "a" * 16


@pytest.mark.parametrize("value", ["off"])
def test_image_extraction_env_switch(service, tmp_path, monkeypatch, value):
    from advancesearch.config import reset_settings_cache
    from advancesearch.ingest import get_document_service

    monkeypatch.setenv("IMAGE_EXTRACTION", value)
    reset_settings_cache()
    svc = get_document_service()
    result = upload(svc, architecture_pdf(tmp_path))
    assert svc.get(result.name).images == 0
    assert svc.pending(include_finished=True) == []  # nothing to upgrade while extraction is off
    assert json.loads(json.dumps(factory.get_image_store().manifest(result.doc_id))) == []
