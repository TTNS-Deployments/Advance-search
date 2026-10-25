import io
from datetime import datetime, timedelta, timezone

import pytest
from helpers import make_blank_pdf, make_docx, make_pdf, make_xlsx, upload

from advancesearch import ingest
from advancesearch.ingest import (FAILED, INDEXED, NO_TEXT, PROCESSING, QUEUED, UploadError, doc_id_for,
                                  sanitize_filename)


def statuses_seen(service, monkeypatch):
    seen = []
    original = service.blobs.set_metadata

    def spy(container, name, metadata, if_match=None):
        seen.append(metadata.get("status"))
        return original(container, name, metadata, if_match)

    monkeypatch.setattr(service.blobs, "set_metadata", spy)
    return seen


def chunk_count(service, name):
    return service.index.document_chunk_count(doc_id_for(name))


# ---------------------------------------------------------------------------- upload validation

@pytest.mark.parametrize("name,expected", [
    ("Leave Policy.pdf", "Leave Policy.pdf"),
    ("../../etc/passwd.pdf", "passwd.pdf"),
    ("C:\\Users\\me\\Report Q1.DOCX", "Report Q1.docx"),
    ("Résumé – final.xlsx", "Resume_final.xlsx"),
    ("<script>.pdf", "script.pdf"),
    ("....pdf", "document.pdf"),
    ("a" * 300 + ".pdf", "a" * 116 + ".pdf"),
])
def test_sanitize_filename(name, expected):
    assert sanitize_filename(name) == expected


def test_upload_rejects_wrong_type(service):
    with pytest.raises(UploadError, match="Only PDF"):
        service.upload("notes.txt", io.BytesIO(b"hello"), 5, "Admin")


def test_upload_rejects_wrong_magic_bytes(service):
    with pytest.raises(UploadError, match="not a valid .pdf"):
        service.upload("fake.pdf", io.BytesIO(b"PK\x03\x04 not a pdf"), 20, "Admin")
    with pytest.raises(UploadError, match="not a valid .docx"):
        service.upload("fake.docx", io.BytesIO(b"%PDF-1.4 not a zip"), 20, "Admin")


def test_upload_rejects_xlsx_renamed_as_docx(service, tmp_path):
    path = make_xlsx(tmp_path / "book.xlsx", {"S": [["H"], ["v"]]})
    with pytest.raises(UploadError, match="not a valid .docx"):
        service.upload("book.docx", path.open("rb"), path.stat().st_size, "Admin")


def test_upload_rejects_too_large_and_empty(service, monkeypatch):
    with pytest.raises(UploadError, match="20 MB"):
        service.upload("big.pdf", io.BytesIO(b"%PDF-"), 21 * 1024 * 1024, "Admin")
    with pytest.raises(UploadError, match="empty"):
        service.upload("empty.pdf", io.BytesIO(b""), 0, "Admin")


# ---------------------------------------------------------------------------- state machine

def test_queued_processing_indexed(service, tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "Leave.pdf", ["Annual entitlement is 24 days.", "Sick leave is 12 days."])
    result = upload(service, path, process=False)
    doc = service.get(result.name)
    assert doc.status == QUEUED and doc.uploaded_by == "Admin" and doc.content_hash
    seen = statuses_seen(service, monkeypatch)
    assert service.process(result.name) == INDEXED
    assert seen == [PROCESSING, INDEXED]
    doc = service.get(result.name)
    assert doc.status == INDEXED and doc.chunks == 2 and doc.error == "" and doc.indexed_at
    assert chunk_count(service, result.name) == 2
    assert "claimed_by" not in service.blobs.info("documents", result.name).metadata


def test_no_text_document(service, tmp_path):
    result = upload(service, make_blank_pdf(tmp_path / "scan.pdf"))
    assert service.process(result.name) == NO_TEXT
    doc = service.get(result.name)
    assert doc.status == NO_TEXT and doc.chunks == 0
    assert doc.error == "No searchable text found. This file may be a scan."


def test_failed_document_keeps_error(service, tmp_path):
    service.blobs.put_bytes("documents", "broken.pdf", b"%PDF-1.7 garbage that is not a pdf")
    assert service.process("broken.pdf") == FAILED
    doc = service.get("broken.pdf")
    assert doc.status == FAILED and "could not be read" in doc.error


def test_embedding_failure_marks_failed_and_removes_partial_chunks(service, tmp_path, monkeypatch):
    path = make_pdf(tmp_path / "doc.pdf", ["Page one text.", "Page two text."])
    result = upload(service, path, process=False)
    attempts = {"n": 0}
    original = service.embedder.embed

    def flaky(texts):
        attempts["n"] += 1
        if attempts["n"] > 1:
            raise RuntimeError("HTTP 500 from embeddings")
        return original(texts)

    monkeypatch.setattr(service.settings_store.__class__, "batch_size", property(lambda self: 1))
    monkeypatch.setattr(service.embedder, "embed", flaky)
    assert service.process(result.name) == FAILED
    assert "HTTP 500" in service.get(result.name).error
    assert chunk_count(service, result.name) == 0


def test_duplicate_upload_says_already_indexed(service, tmp_path):
    path = make_pdf(tmp_path / "a.pdf", ["Unique content here."])
    upload(service, path)
    copy = tmp_path / "copy-of-a.pdf"
    copy.write_bytes(path.read_bytes())
    with pytest.raises(UploadError, match="already indexed as a.pdf"):
        upload(service, copy)
    assert [d.name for d in service.list()] == ["a.pdf"]


def test_duplicate_dropped_in_storage_is_not_indexed_twice(service, tmp_path):
    path = make_pdf(tmp_path / "a.pdf", ["Unique content here."])
    upload(service, path)
    service.blobs.put_bytes("documents", "b.pdf", path.read_bytes())
    assert service.process("b.pdf") == FAILED
    assert "already indexed as a.pdf" in service.get("b.pdf").error
    assert chunk_count(service, "b.pdf") == 0


def test_same_name_new_content_replaces_document(service, tmp_path):
    upload(service, make_pdf(tmp_path / "plan.pdf", ["Version one.", "Second page."]))
    assert chunk_count(service, "plan.pdf") == 2
    result = upload(service, make_pdf(tmp_path / "plan.pdf", ["Version two only."]))
    assert result.replaced
    assert chunk_count(service, "plan.pdf") == 1


def test_delete_removes_blob_and_all_chunks(service, tmp_path):
    upload(service, make_docx(tmp_path / "keep.docx", [("h1", "A"), ("p", "Keep me."), ("h1", "B"), ("p", "Me too.")]))
    upload(service, make_docx(tmp_path / "gone.docx", [("h1", "A"), ("p", "Delete me."), ("h1", "B"), ("p", "Bye.")]))
    assert chunk_count(service, "gone.docx") == 2
    assert service.delete("gone.docx") == 2
    assert service.get("gone.docx") is None
    assert chunk_count(service, "gone.docx") == 0
    assert chunk_count(service, "keep.docx") == 2


def test_reindex_and_rebuild(service, tmp_path, monkeypatch):
    upload(service, make_pdf(tmp_path / "a.pdf", ["Alpha text."]))
    upload(service, make_xlsx(tmp_path / "b.xlsx", {"S": [["Item", "Price"], ["Paper", 5]]}))
    service.reindex("a.pdf")
    assert service.get("a.pdf").status == QUEUED
    assert service.process("a.pdf") == INDEXED
    names = service.rebuild_index()
    assert sorted(names) == ["a.pdf", "b.xlsx"]
    assert all(d.status == QUEUED for d in service.list())
    assert service.index.status().chunks == 0
    for name in names:
        service.process(name)
    assert service.index.status().chunks == 2


# ---------------------------------------------------------------------------- claims and recovery

def test_two_processes_cannot_claim_the_same_file(service, tmp_path, monkeypatch):
    result = upload(service, make_pdf(tmp_path / "a.pdf", ["Text."]), process=False)
    stale_etag = service.blobs.info("documents", result.name).etag
    assert service.claim(result.name)  # first process wins
    # A second process that read the blob before the claim fails its conditional update.
    from advancesearch.storage import PreconditionFailed

    with pytest.raises(PreconditionFailed):
        service.blobs.set_metadata("documents", result.name, {"status": PROCESSING}, if_match=stale_etag)
    assert not service.claim(result.name)  # and a fresh claim sees the live claim


def _set_claim(service, name, claimed_by, minutes_ago):
    meta = dict(service.blobs.info("documents", name).metadata)
    at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta.update(status=PROCESSING, claimed_by=claimed_by, claimed_at=at)
    service.blobs.set_metadata("documents", name, meta)


def test_restart_recovery(service, tmp_path, monkeypatch):
    for n in ("same-host.pdf", "other-host-fresh.pdf", "other-host-stale.pdf", "new.pdf"):
        upload(service, make_pdf(tmp_path / n, [f"Content of {n}."]), process=False)
    _set_claim(service, "same-host.pdf", f"{ingest.INSTANCE}:99999:dead0000", 1)    # this host, old process
    _set_claim(service, "other-host-fresh.pdf", "otherhost:1:abcd", 1)               # alive elsewhere
    _set_claim(service, "other-host-stale.pdf", "otherhost:1:abcd", 60)              # abandoned
    pending = service.pending(include_finished=True)
    assert sorted(pending) == ["new.pdf", "other-host-stale.pdf", "same-host.pdf"]
    assert service.process("other-host-fresh.pdf") is None  # claimed elsewhere: skipped
    assert service.process("same-host.pdf") == INDEXED


def test_sync_includes_failed_and_no_text_but_periodic_scan_does_not(service, tmp_path):
    upload(service, make_blank_pdf(tmp_path / "scan.pdf"))
    service.blobs.put_bytes("documents", "dropped.pdf", make_pdf(tmp_path / "x.pdf", ["Dropped in storage."]).read_bytes())
    service.blobs.put_bytes("documents", "readme.txt", b"ignored")
    assert service.pending(include_finished=False) == ["dropped.pdf"]
    assert sorted(service.pending(include_finished=True)) == ["dropped.pdf", "scan.pdf"]


def test_document_info_for_blob_without_metadata(service, tmp_path):
    service.blobs.put_bytes("documents", "seeded.xlsx", make_xlsx(tmp_path / "s.xlsx", {"S": [["H"], ["v"]]}).read_bytes())
    doc = service.get("seeded.xlsx")
    assert doc.status == QUEUED and doc.uploaded_by == "storage" and doc.uploaded_at is not None
    assert service.find(doc.doc_id) == doc
    assert service.find(doc.doc_id, "seeded.xlsx") == doc
    assert service.find(doc.doc_id, "other.xlsx") is None


def test_worker_threads_process_queue_and_start_up_scan(service, tmp_path, monkeypatch):
    import time

    from advancesearch.worker import Worker

    service.blobs.put_bytes("documents", "dropped.pdf", make_pdf(tmp_path / "x.pdf", ["Dropped in storage."]).read_bytes())
    worker = Worker(lambda: service, mode="thread", sync_interval=60)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while service.get("dropped.pdf").status != INDEXED and time.monotonic() < deadline:
            time.sleep(0.05)
        assert service.get("dropped.pdf").status == INDEXED
        result = upload(service, make_pdf(tmp_path / "later.pdf", ["Uploaded later."]), process=False)
        worker.enqueue(result.name)
        worker.enqueue(result.name)  # de-duplicated
        while service.get(result.name).status != INDEXED and time.monotonic() < deadline:
            time.sleep(0.05)
        assert service.get(result.name).status == INDEXED
    finally:
        worker.stop()
