"""Settings store, embeddings clients and the Azure AI Search adapter (with the SDK replaced by fakes)."""
import json
from types import SimpleNamespace

import pytest

from advancesearch import factory
from advancesearch.config import Settings, get_settings
from advancesearch.embeddings import AzureOpenAIEmbeddings, EmbeddingError, MockEmbeddings
from advancesearch.settings_store import SettingsError, validate

# ---------------------------------------------------------------------------- settings store


def test_defaults_come_from_search_yaml():
    values = factory.get_settings_store().effective()
    assert values["top_n"] == 3 and values["min_match_percent"] == 20
    assert "how many days off do I get" in values["example_queries"]
    assert values["welcome_text"]


def test_overrides_saved_in_config_container():
    store = factory.get_settings_store()
    store.save({"top_n": "5", "min_match_percent": 35, "example_queries": "one\n\n two \n", "welcome_text": " Hi "})
    saved = json.loads(factory.get_blob_store().get_bytes("config", "settings.json"))
    assert saved == {"top_n": 5, "min_match_percent": 35, "example_queries": ["one", "two"], "welcome_text": "Hi"}
    factory.reset()  # a new process reads the same overrides
    assert factory.get_settings_store().effective()["top_n"] == 5
    factory.get_settings_store().reset()
    assert factory.get_settings_store().effective()["top_n"] == 3


@pytest.mark.parametrize("values,message", [
    ({"top_n": 0}, "between 1 and 10"), ({"top_n": 11}, "between 1 and 10"), ({"top_n": "x"}, "whole number"),
    ({"min_match_percent": 101}, "between 0 and 100"), ({"min_match_percent": -1}, "between 0 and 100"),
    ({"example_queries": [str(i) for i in range(13)]}, "at most 12"), ({"welcome_text": "x" * 501}, "500"),
])
def test_settings_validation(values, message):
    with pytest.raises(SettingsError, match=message):
        validate(values)


def test_broken_overrides_file_falls_back_to_defaults():
    factory.get_blob_store().put_bytes("config", "settings.json", b"{not json")
    assert factory.get_settings_store().effective()["top_n"] == 3


def test_key_vault_reference_treated_as_empty(monkeypatch):
    from advancesearch.config import reset_settings_cache

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "@Microsoft.KeyVault(VaultName=kv;SecretName=x)")
    reset_settings_cache()
    assert get_settings().openai_endpoint == ""


def test_mode_sets_backend_defaults(monkeypatch):
    from advancesearch.config import reset_settings_cache

    monkeypatch.setenv("ADVSEARCH_MODE", "azure")
    monkeypatch.setenv("EMBEDDING_BACKEND", "mock")
    reset_settings_cache()
    s = get_settings()
    assert (s.storage_backend, s.search_backend, s.embedding_backend) == ("azure", "azure", "mock")
    monkeypatch.setenv("ADVSEARCH_MODE", "cloud")
    reset_settings_cache()
    with pytest.raises(ValueError, match="ADVSEARCH_MODE"):
        get_settings()


# ---------------------------------------------------------------------------- embeddings

def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def test_mock_embeddings_are_deterministic_and_meaningful():
    emb = MockEmbeddings(256, [["days off", "leave", "annual entitlement"]])
    q = emb.embed_query("how many days off do I get")
    assert q == emb.embed_query("how many days off do I get")
    related = emb.embed_query("Your annual entitlement of leave is 24 working days.")
    unrelated = emb.embed_query("The tablet battery lasts 14 hours on one charge.")
    assert _cos(q, related) > _cos(q, unrelated) + 0.1
    assert abs(_cos(q, q) - 1.0) < 1e-9


class FakeResponse:
    def __init__(self, status, body=None, headers=None):
        self.status_code, self._body, self.headers = status, body or {}, headers or {}
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _azure_settings(**kw):
    return Settings(embedding_backend="azure", openai_endpoint="https://example.openai.azure.com", openai_key="k",
                    embedding_dimensions=3, **kw)


def ok(n):
    return FakeResponse(200, {"data": [{"index": i, "embedding": [0.1 * i, 0.2, 0.3]} for i in reversed(range(n))]})


def test_azure_embeddings_retry_on_429_and_5xx():
    import requests

    sleeps = []
    session = FakeSession([FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(503),
                           requests.ConnectionError("reset"), ok(2)])
    client = AzureOpenAIEmbeddings(_azure_settings(), session=session, sleep=sleeps.append)
    vectors = client.embed(["a", "b"])
    assert vectors == [[0.0, 0.2, 0.3], [0.1, 0.2, 0.3]]  # ordered by index
    assert sleeps[0] == 2.0 and len(sleeps) == 3
    call = session.calls[0]
    assert "/openai/deployments/text-embedding-3-small/embeddings?api-version=2024-10-21" in call["url"]
    assert call["json"] == {"input": ["a", "b"], "dimensions": 3}
    assert call["headers"] == {"api-key": "k"}


def test_azure_embeddings_do_not_retry_client_errors():
    session = FakeSession([FakeResponse(400, {"error": "bad"})])
    with pytest.raises(EmbeddingError, match="HTTP 400"):
        AzureOpenAIEmbeddings(_azure_settings(), session=session, sleep=lambda s: None).embed(["a"])
    assert len(session.calls) == 1


def test_azure_embeddings_give_up_after_max_attempts():
    session = FakeSession([FakeResponse(429)] * 6)
    with pytest.raises(EmbeddingError, match="after 6 attempts"):
        AzureOpenAIEmbeddings(_azure_settings(), session=session, sleep=lambda s: None).embed(["a"])


def test_azure_embeddings_check_dimensions():
    session = FakeSession([FakeResponse(200, {"data": [{"index": 0, "embedding": [1.0] * 5}]})])
    with pytest.raises(EmbeddingError, match="returned 5 dimensions"):
        AzureOpenAIEmbeddings(_azure_settings(), session=session, sleep=lambda s: None).embed(["a"])


# ---------------------------------------------------------------------------- Azure AI Search adapter

class FakeSearchClient:
    def __init__(self, hybrid_rows, vector_rows=None, fail_semantic=False):
        self.hybrid_rows, self.vector_rows, self.fail_semantic = hybrid_rows, vector_rows or [], fail_semantic
        self.calls, self.deleted, self.uploaded = [], [], []

    def search(self, **kwargs):
        from azure.core.exceptions import HttpResponseError

        self.calls.append(kwargs)
        if kwargs.get("filter"):
            return [{"id": "d1-00000"}, {"id": "d1-00001"}] if not self.deleted else []
        if kwargs.get("search_text") is None:
            return self.vector_rows
        if kwargs.get("query_type") == "semantic" and self.fail_semantic:
            raise HttpResponseError(message="Semantic search is not enabled for this service.")
        return self.hybrid_rows

    def delete_documents(self, docs):
        self.deleted.extend(docs)

    def merge_or_upload_documents(self, docs):
        self.uploaded.extend(docs)
        return [SimpleNamespace(succeeded=True, error_message="") for _ in docs]

    def get_document_count(self):
        return 2


def _row(i, reranker=None, score=0.03):
    row = {"id": f"d{i}-00000", "docId": f"d{i}", "fileName": f"f{i}.pdf", "fileType": "pdf", "location": "Page 1",
           "chunkIndex": 0, "uploadedAt": "2026-01-01T00:00:00Z", "content": "text", "@search.score": score}
    if reranker is not None:
        row["@search.reranker_score"] = reranker
    return row


@pytest.fixture
def azure_index(monkeypatch):
    from advancesearch.index import AzureSearchIndex, IndexStatus

    monkeypatch.setenv("SEARCH_API_KEY", "test-key")
    idx = AzureSearchIndex(Settings(search_backend="azure", search_endpoint="https://x.search.windows.net",
                                    search_api_key="k", embedding_dimensions=3))
    idx._ensured = IndexStatus(True, 3, 3)
    return idx


def test_index_definition(azure_index):
    definition = azure_index.definition()
    fields = {f.name: f for f in definition.fields}
    assert list(fields) == ["id", "docId", "fileName", "fileType", "location", "chunkIndex", "uploadedAt",
                            "content", "contentVector"]
    assert fields["id"].key and fields["docId"].filterable
    assert fields["fileType"].filterable and fields["fileType"].facetable
    assert fields["uploadedAt"].filterable and fields["uploadedAt"].sortable
    assert fields["content"].searchable and fields["content"].analyzer_name == "en.microsoft"
    assert fields["contentVector"].vector_search_dimensions == 3
    assert definition.vector_search.algorithms[0].parameters.metric == "cosine"
    config = definition.semantic_search.configurations[0]
    assert config.prioritized_fields.title_field.field_name == "fileName"
    assert config.prioritized_fields.content_fields[0].field_name == "content"


def test_azure_search_uses_reranker_scores(azure_index):
    azure_index.client = FakeSearchClient([_row(1, reranker=3.1), _row(2, reranker=1.0)])
    hits = azure_index.search("leave", [0.1, 0.2, 0.3], 50)
    assert [h.reranker_score for h in hits] == [3.1, 1.0]
    call = azure_index.client.calls[0]
    assert call["query_type"] == "semantic" and call["top"] == 50
    assert call["vector_queries"][0].k_nearest_neighbors == 50
    assert len(azure_index.client.calls) == 1  # no extra vector query needed


def test_azure_search_falls_back_to_cosine_without_reranker(azure_index):
    # Partial semantic response (quota used up): no reranker scores; cosine from a vector-only query.
    azure_index.client = FakeSearchClient([_row(1), _row(2)], vector_rows=[
        {"id": "d1-00000", "@search.score": 1 / (1 + (1 - 0.8))}, {"id": "d2-00000", "@search.score": 1 / (1 + 0.5)}])
    hits = azure_index.search("leave", [0.1, 0.2, 0.3], 50)
    assert [round(h.cosine, 6) for h in hits] == [0.8, 0.5]
    assert all(h.reranker_score is None for h in hits)


def test_azure_search_retries_without_semantic_when_disabled(azure_index):
    azure_index.client = FakeSearchClient([_row(1)], vector_rows=[{"id": "d1-00000", "@search.score": 0.9}],
                                          fail_semantic=True)
    hits = azure_index.search("leave", [0.1, 0.2, 0.3], 50)
    assert hits[0].reranker_score is None and hits[0].cosine is not None
    assert "query_type" not in azure_index.client.calls[1]
    azure_index.search("leave", [0.1, 0.2, 0.3], 50)  # remembered: no semantic attempt for a while
    assert all(c.get("query_type") != "semantic" for c in azure_index.client.calls[2:])


def test_azure_delete_document_filters_on_doc_id(azure_index):
    azure_index.client = FakeSearchClient([])
    assert azure_index.delete_document("d1") == 2
    assert azure_index.client.calls[0]["filter"] == "docId eq 'd1'"
    with pytest.raises(ValueError):
        azure_index.delete_document("x' or true or '")


def test_index_dimension_mismatch_is_reported(azure_index):
    from advancesearch.index import IndexMismatch, IndexStatus

    azure_index._ensured = None
    azure_index._existing = lambda: SimpleNamespace(fields=[SimpleNamespace(name="contentVector",
                                                                            vector_search_dimensions=3072)],
                                                     semantic_search=object())
    status = azure_index.ensure()
    assert status.mismatch and "3072" in status.warning and "Rebuild" in status.warning
    with pytest.raises(IndexMismatch):
        azure_index.upload([{"id": "x"}])
    assert IndexStatus(True, 3, 3).warning == ""


def test_local_index_dimension_mismatch(tmp_path):
    from advancesearch.index import IndexMismatch, LocalIndex

    LocalIndex(tmp_path / "i.sqlite3", 64).ensure()
    other = LocalIndex(tmp_path / "i.sqlite3", 128)
    assert other.status().mismatch
    with pytest.raises(IndexMismatch):
        other.search("q", [0.0] * 128)
    other.reset()
    assert not other.status().mismatch
