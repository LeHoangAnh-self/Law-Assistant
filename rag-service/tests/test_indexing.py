import httpx
from qdrant_client.http.exceptions import ResponseHandlingException
from rag_service.config import Settings
from rag_service.indexing import DocumentIndexer
from rag_service.models import SourceReference
from rag_service.pipeline import RagPipeline


class FakeLawClient:
    def __init__(self) -> None:
        self.status_updates: list[tuple[int, str]] = []

    def get_document_detail_sync(self, document_id: int) -> dict:
        return {
            "document": {
                "id": document_id,
                "title": "Luật mẫu",
                "documentNumber": "01/2026/QH",
                "documentType": "Luật",
                "validityStatus": "Còn hiệu lực",
                "issuedDate": "2026-01-01",
                "effectiveDate": "2026-02-01",
                "expiredDate": None,
                "issuingAuthority": "Quốc hội",
                "scope": "Toàn quốc",
                "source": "Law Service",
                "sourceUrl": "https://vanban.chinhphu.vn/?docid=123",
                "externalSource": "vanban.chinhphu.vn",
                "externalDocid": "123",
            },
            "contentText": "Điều 1. Hiệu lực\nVăn bản này có hiệu lực từ ngày ký.",
        }

    def update_embedding_status_sync(self, document_id: int, status: str) -> None:
        self.status_updates.append((document_id, status))


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen_texts = texts
        return [[0.1, 0.2] for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.delete_existing = None

    def replace_document_chunks(
        self,
        document_id: int,
        chunks: list[dict],
        vectors: list[list[float]],
        delete_existing: bool = False,
    ) -> int:
        self.payloads = chunks
        self.delete_existing = delete_existing
        assert document_id == 42
        assert vectors == [[0.1, 0.2] for _ in chunks]
        assert delete_existing is True
        return len(chunks)


def test_indexer_embeds_enriched_retrieval_text_and_stores_legal_metadata() -> None:
    embedding_model = FakeEmbeddingModel()
    vector_store = FakeVectorStore()
    law_client = FakeLawClient()
    indexer = DocumentIndexer(
        Settings(embedding_dimension=2),
        law_client=law_client,
        embedding_model=embedding_model,
        vector_store=vector_store,
    )

    indexed_count = indexer.index_document(42)

    assert indexed_count == 1
    assert law_client.status_updates == [(42, "INDEXING"), (42, "INDEXED")]
    assert embedding_model.seen_texts
    assert "Tiêu đề: Luật mẫu" in embedding_model.seen_texts[0]
    assert "Cơ quan ban hành: Quốc hội" in embedding_model.seen_texts[0]
    assert "Phạm vi: Toàn quốc" in embedding_model.seen_texts[0]
    assert "Mã nguồn ngoài: 123" in embedding_model.seen_texts[0]
    assert "Vị trí pháp lý: Điều 1. Hiệu lực" in embedding_model.seen_texts[0]
    assert (
        vector_store.payloads[0]["text"]
        == "Điều 1. Hiệu lực\nVăn bản này có hiệu lực từ ngày ký."
    )
    assert vector_store.payloads[0]["retrieval_text"] == embedding_model.seen_texts[0]
    assert vector_store.payloads[0]["document_type"] == "Luật"
    assert vector_store.payloads[0]["validity_status"] == "Còn hiệu lực"
    assert vector_store.payloads[0]["effective_date"] == "2026-02-01"
    assert vector_store.payloads[0]["issuing_authority"] == "Quốc hội"
    assert vector_store.payloads[0]["scope"] == "Toàn quốc"
    assert vector_store.payloads[0]["source_url"] == "https://vanban.chinhphu.vn/?docid=123"
    assert vector_store.payloads[0]["external_source"] == "vanban.chinhphu.vn"
    assert vector_store.payloads[0]["external_docid"] == "123"
    assert vector_store.payloads[0]["article_number"] == "1"
    assert vector_store.payloads[0]["chunk_level"] == "parent"
    assert vector_store.payloads[0]["parent_id"] == "42:0"
    assert vector_store.payloads[0]["parent_article_number"] == "1"
    assert vector_store.payloads[0]["parent_text"] == vector_store.payloads[0]["text"]
    assert vector_store.payloads[0]["chunking_strategy"] == "legal_structure_v1"


def test_indexer_stores_parent_and_child_payloads_with_document_metadata() -> None:
    class ClauseLawClient(FakeLawClient):
        def get_document_detail_sync(self, document_id: int) -> dict:
            detail = super().get_document_detail_sync(document_id)
            detail["contentText"] = (
                "Điều 2. Nghĩa vụ\n"
                "1. Cá nhân cung cấp thông tin.\n"
                "2. Cơ quan trả lời đúng hạn."
            )
            return detail

    embedding_model = FakeEmbeddingModel()
    vector_store = FakeVectorStore()
    law_client = ClauseLawClient()
    indexer = DocumentIndexer(
        Settings(embedding_dimension=2, chunk_size=500, chunk_overlap=50),
        law_client=law_client,
        embedding_model=embedding_model,
        vector_store=vector_store,
    )

    indexed_count = indexer.index_document(42)

    assert indexed_count == 3
    parent = vector_store.payloads[0]
    children = vector_store.payloads[1:]
    assert parent["chunk_level"] == "parent"
    assert parent["parent_id"] == parent["chunk_id"]
    assert parent["parent_article_number"] == "2"
    assert parent["document_type"] == "Luật"
    assert [child["chunk_level"] for child in children] == ["child", "child"]
    assert [child["parent_id"] for child in children] == [parent["chunk_id"], parent["chunk_id"]]
    assert [child["clause_number"] for child in children] == ["1", "2"]
    assert all(child["article_number"] == "2" for child in children)
    assert all(child["parent_article_number"] == "2" for child in children)
    assert all(child["parent_text"] == parent["text"] for child in children)
    assert "Cá nhân cung cấp thông tin" in children[0]["child_text"]
    assert embedding_model.seen_texts == [
        payload["retrieval_text"] for payload in vector_store.payloads
    ]
    assert law_client.status_updates == [(42, "INDEXING"), (42, "INDEXED")]


def test_multiple_child_hits_from_same_article_dedupe_to_one_parent_article() -> None:
    first = SourceReference(
        document_id=42,
        chunk_id="42:1",
        parent_id="42:0",
        parent_article_number="2",
        article_number="2",
        clause_number="1",
        chunk_level="child",
        score=0.91,
        text=(
            "Điều 2. Nghĩa vụ\n"
            "1. Cá nhân cung cấp thông tin.\n"
            "2. Cơ quan trả lời đúng hạn."
        ),
        child_text="Điều 2. Nghĩa vụ\n1. Cá nhân cung cấp thông tin.",
        parent_text=(
            "Điều 2. Nghĩa vụ\n"
            "1. Cá nhân cung cấp thông tin.\n"
            "2. Cơ quan trả lời đúng hạn."
        ),
    )
    second = first.model_copy(
        update={
            "chunk_id": "42:2",
            "clause_number": "2",
            "score": 0.88,
            "child_text": "Điều 2. Nghĩa vụ\n2. Cơ quan trả lời đúng hạn.",
        }
    )

    deduped = RagPipeline._dedupe_parent_article_references([first, second])

    assert deduped == [first]


def test_indexer_passes_qdrant_write_settings(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class CapturingVectorStore(FakeVectorStore):
        def __init__(
            self,
            url: str,
            collection_name: str,
            vector_size: int,
            timeout: float,
            upsert_batch_size: int,
        ) -> None:
            captured["url"] = url
            captured["collection_name"] = collection_name
            captured["vector_size"] = vector_size
            captured["timeout"] = timeout
            captured["upsert_batch_size"] = upsert_batch_size

    monkeypatch.setattr("rag_service.indexing.QdrantVectorStore", CapturingVectorStore)

    DocumentIndexer(
        Settings(
            embedding_dimension=2,
            qdrant_timeout_seconds=180.0,
            qdrant_upsert_batch_size=17,
        ),
        law_client=FakeLawClient(),
        embedding_model=FakeEmbeddingModel(),
    )

    assert captured["timeout"] == 180.0
    assert captured["upsert_batch_size"] == 17


def test_indexer_marks_document_failed_when_indexing_raises() -> None:
    class FailingEmbeddingModel(FakeEmbeddingModel):
        def embed(self, texts: list[str]) -> list[list[float]]:
            _ = texts
            raise RuntimeError("embedding failed")

    law_client = FakeLawClient()
    indexer = DocumentIndexer(
        Settings(embedding_dimension=2),
        law_client=law_client,
        embedding_model=FailingEmbeddingModel(),
        vector_store=FakeVectorStore(),
    )

    try:
        indexer.index_document(42)
    except RuntimeError:
        pass

    assert law_client.status_updates == [(42, "INDEXING"), (42, "FAILED")]


def test_indexer_does_not_mark_retryable_qdrant_failure_failed() -> None:
    class UnavailableVectorStore(FakeVectorStore):
        def replace_document_chunks(
            self,
            document_id: int,
            chunks: list[dict],
            vectors: list[list[float]],
            delete_existing: bool = False,
        ) -> int:
            _ = document_id, chunks, vectors, delete_existing
            raise ResponseHandlingException(httpx.ConnectError("[Errno 111] Connection refused"))

    law_client = FakeLawClient()
    indexer = DocumentIndexer(
        Settings(embedding_dimension=2),
        law_client=law_client,
        embedding_model=FakeEmbeddingModel(),
        vector_store=UnavailableVectorStore(),
    )

    try:
        indexer.index_document(42)
    except ResponseHandlingException:
        pass

    assert law_client.status_updates == [(42, "INDEXING")]
