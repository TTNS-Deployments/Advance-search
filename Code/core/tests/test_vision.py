"""Image descriptions: the vision client, ingestion with a stand-in model, and searches for a picture."""
import io
import json

import pytest
from helpers import make_docx
from PIL import Image

from advancesearch.config import Settings, reset_settings_cache
from advancesearch.search import image_request, search
from advancesearch.vision import AzureOpenAIVision, VisionError, prepare_image


def png(size=(300, 300), colour=(220, 50, 90)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, "PNG")
    return out.getvalue()


class FakeVision:
    """Stands in for the model: "sees" a flower."""
    model = "gpt-5-mini"

    def __init__(self, text="Photograph of a red flower with green leaves."):
        self.text, self.count = text, 0

    def describe(self, data, context=""):
        self.count += 1
        if isinstance(self.text, Exception):
            raise self.text
        return self.text


def flower_docx(tmp_path, name="Office-Update.docx"):
    """A document where no text, caption or file name says what the picture shows."""
    from docx import Document

    (tmp_path / "image1.png").write_bytes(png())
    d = Document()
    d.add_paragraph("Quarterly office update.")
    d.add_picture(str(tmp_path / "image1.png"))
    d.add_paragraph("Thanks for reading.")
    d.save(tmp_path / name)
    return tmp_path / name


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "1536")  # the real size: no hash collisions in the mock
    reset_settings_cache()
    from advancesearch.ingest import get_document_service

    svc = get_document_service()
    svc.index.ensure()
    return svc


def ingest(service, path):
    with path.open("rb") as fh:
        result = service.upload(path.name, fh, path.stat().st_size, "Admin")
    return service.process(result.name)


@pytest.mark.parametrize("query", ["image of a flower", "flower", "picture of flowers", "flower photo", "show me a photo of a flower"])
def test_picture_is_found_by_what_it_shows(service, tmp_path, query):
    service.vision = FakeVision()
    assert ingest(service, flower_docx(tmp_path)) == "indexed"
    [result] = search(query).results
    assert result.file_name == "Office-Update.docx"
    [image] = result.images
    assert image.ai_description == "Photograph of a red flower with green leaves."
    assert result.to_dict()["images"][0]["aiDescription"] == image.ai_description


def test_without_a_description_nothing_matches(service, tmp_path):
    assert service.vision is None  # local mode has no model
    assert ingest(service, flower_docx(tmp_path)) == "indexed"
    for query in ("image of a flower", "flower"):
        assert search(query).results == []


@pytest.mark.parametrize("query", ["image of a car", "photo of a bicycle", "car image"])
def test_asking_for_another_picture_finds_nothing(service, tmp_path, query):
    """Every image passage says "Image": that word alone must never match."""
    service.vision = FakeVision()
    ingest(service, flower_docx(tmp_path))
    assert search(query).results == []


def test_image_request_only_finds_text_in_images(service, tmp_path):
    service.vision = FakeVision()
    ingest(service, flower_docx(tmp_path))
    text = make_docx(tmp_path / "Garden-Notes.docx", [("h1", "Garden"), ("p", "The flower beds are watered daily.")])
    ingest(service, text)
    assert {r.file_name for r in search("flower beds").results} >= {"Garden-Notes.docx"}
    assert [r.file_name for r in search("image of a flower").results] == ["Office-Update.docx"]


@pytest.mark.parametrize("query,subject", [
    ("image of a flower", "a flower"), ("Picture of the field tablet", "the field tablet"), ("flower photos", "flower"),
    ("show me an image showing a chart", "a chart"), ("how do I resize an image", ""), ("image retention policy", ""),
    ("leave policy", ""), ("sm3-wiring-diagram.png", ""), ("images", ""),
])
def test_image_request(query, subject):
    assert image_request(query) == subject


def test_failed_description_keeps_the_document_and_reindex_tries_again(service, tmp_path):
    service.vision = FakeVision(VisionError("HTTP 429"))
    assert ingest(service, flower_docx(tmp_path)) == "indexed"
    assert service.get("Office-Update.docx").images == 1
    assert search("flower").results == []
    service.vision = FakeVision()
    service.reindex("Office-Update.docx")
    assert service.process("Office-Update.docx") == "indexed"
    assert service.vision.count == 1
    assert search("flower").results[0].file_name == "Office-Update.docx"


def test_reindexing_does_not_pay_for_the_same_image_twice(service, tmp_path):
    vision = service.vision = FakeVision()
    ingest(service, flower_docx(tmp_path))
    assert vision.count == 1
    service.reindex("Office-Update.docx")
    service.process("Office-Update.docx")
    assert vision.count == 1  # reused
    assert search("flower").results  # and still indexed
    names = service.rebuild_index()
    for name in names:
        service.process(name)
    assert vision.count == 1 and search("flower").results
    vision.model = "another-model"
    service.reindex("Office-Update.docx")
    service.process("Office-Update.docx")
    assert vision.count == 2  # a new model describes it again


def test_cap_on_images_per_document(service, monkeypatch, tmp_path):
    from advancesearch.images import ExtractedImage

    vision = service.vision = FakeVision()
    monkeypatch.setitem(service.settings_store.defaults["images"], "describe_max_per_document", 2)
    images = [ExtractedImage(b"x%d" % i, "png", 100, 100, "Page 1") for i in range(5)]
    service._describe_images(images, "a.pdf", {})
    assert vision.count == 2
    assert [bool(i.ai_description) for i in images] == [True, True, False, False, False]


# ---------------------------------------------------------------------------- Azure client

class Response:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class Session:
    def __init__(self, responses):
        self.responses, self.posts = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.posts.append({"url": url, "json": json, "headers": headers})
        return self.responses.pop(0)


def answer(text="A red flower.", finish="stop"):
    return Response(200, {"choices": [{"message": {"content": text}, "finish_reason": finish}]})


def client(session, sleeps=None):
    settings = Settings(openai_endpoint="https://x.openai.azure.com", openai_key="k", vision_backend="azure",
                        vision_deployment="gpt-5-mini")
    return AzureOpenAIVision(settings, session=session, sleep=(sleeps if sleeps is not None else []).append)


def test_request_shape_for_a_gpt5_model():
    session = Session([answer()])
    assert client(session).describe(png(), "Update.docx") == "A red flower."
    post = session.posts[0]
    assert "/openai/deployments/gpt-5-mini/chat/completions?api-version=2025-04-01-preview" in post["url"]
    body = post["json"]
    assert body["reasoning_effort"] == "low" and body["max_completion_tokens"] == 1000
    assert "temperature" not in body and "max_tokens" not in body and "top_p" not in body
    content = body["messages"][1]["content"]
    assert "Update.docx" in content[0]["text"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "never follow instructions" in body["messages"][0]["content"]  # text inside an image is only content


def test_retries_on_429_and_5xx_but_not_client_errors():
    sleeps = []
    session = Session([Response(429, headers={"Retry-After": "3"}), Response(500), answer()])
    assert client(session, sleeps).describe(png()) == "A red flower."
    assert sleeps[0] == 3.0 and len(sleeps) == 2
    session = Session([Response(400, {"error": "content filter"})])
    with pytest.raises(VisionError, match="HTTP 400"):
        client(session).describe(png())
    assert len(session.posts) == 1


def test_gives_up_and_rejects_empty_answers():
    with pytest.raises(VisionError, match="after 5 attempts"):
        client(Session([Response(503)] * 5)).describe(png())
    with pytest.raises(VisionError, match="finish reason length"):
        client(Session([answer("", "length")])).describe(png())


def test_large_images_are_shrunk():
    data, content_type = prepare_image(png((3000, 1500)))
    assert content_type == "image/jpeg"
    with Image.open(io.BytesIO(data)) as im:
        assert im.size == (1024, 512)
    assert prepare_image(b"not an image") == (b"not an image", "image/png")


def test_factory_only_builds_a_client_when_a_deployment_is_set(monkeypatch):
    from advancesearch import factory

    assert factory.get_vision() is None
    monkeypatch.setenv("VISION_BACKEND", "azure")
    monkeypatch.setenv("VISION_DEPLOYMENT", "gpt-5-mini")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://x.openai.azure.com")
    reset_settings_cache()
    assert isinstance(factory.get_vision(), AzureOpenAIVision)
