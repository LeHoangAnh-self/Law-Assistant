from rag_service.config import Settings
from rag_service.indexing import DocumentIndexer


class FakeLawClient:
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


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.seen_texts: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.seen_texts = texts
        return [[0.1, 0.2] for _ in texts]


class FakeVectorStore:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def replace_document_chunks(
        self,
        document_id: int,
        chunks: list[dict],
        vectors: list[list[float]],
        delete_existing: bool = False,
    ) -> int:
        self.payloads = chunks
        assert document_id == 42
        assert vectors == [[0.1, 0.2]]
        assert delete_existing is False
        return len(chunks)


def test_indexer_embeds_enriched_retrieval_text_and_stores_legal_metadata() -> None:
    embedding_model = FakeEmbeddingModel()
    vector_store = FakeVectorStore()
    indexer = DocumentIndexer(
        Settings(embedding_dimension=2),
        law_client=FakeLawClient(),
        embedding_model=embedding_model,
        vector_store=vector_store,
    )

    indexed_count = indexer.index_document(42)

    assert indexed_count == 1
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
    assert vector_store.payloads[0]["chunking_strategy"] == "legal_structure_v1"


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
