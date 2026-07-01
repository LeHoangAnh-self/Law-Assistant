from rag_service.chunking import chunk_legal_text
from rag_service.config import Settings
from rag_service.embedding import EmbeddingModel
from rag_service.law_client import LawServiceClient
from rag_service.vector_store import QdrantVectorStore


class DocumentIndexer:
    def __init__(
        self,
        settings: Settings,
        law_client: LawServiceClient | None = None,
        embedding_model: EmbeddingModel | None = None,
        vector_store: QdrantVectorStore | None = None,
    ) -> None:
        self.settings = settings
        self.law_client = law_client or LawServiceClient(str(settings.law_service_base_url))
        self.embedding_model = embedding_model or EmbeddingModel(
            settings.embedding_model_name,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
            local_files_only=settings.embedding_local_files_only,
        )
        self.vector_store = vector_store or QdrantVectorStore(
            str(settings.qdrant_url),
            settings.qdrant_collection,
            settings.embedding_dimension,
            timeout=settings.qdrant_timeout_seconds,
            upsert_batch_size=settings.qdrant_upsert_batch_size,
        )

    def index_document(self, document_id: int) -> int:
        detail = self.law_client.get_document_detail_sync(document_id)
        document = detail["document"]
        text = detail.get("contentText") or document.get("title") or ""
        document_context = self._document_context(document)
        chunks = chunk_legal_text(
            text,
            self.settings.chunk_size,
            self.settings.chunk_overlap,
            document_context=document_context,
        )
        chunk_ids = [f"{document_id}:{index}" for index, _ in enumerate(chunks)]
        parent_ids = {
            chunk.parent_key: chunk_ids[index]
            for index, chunk in enumerate(chunks)
            if chunk.parent_key and chunk.chunk_level == "parent"
        }
        payloads = [
            {
                "chunk_id": chunk_ids[index],
                "document_id": document_id,
                "chunk_index": index,
                "text": chunk.text,
                "retrieval_text": chunk.retrieval_text,
                "char_start": chunk.char_start,
                "char_end": chunk.char_end,
                "legal_path": chunk.legal_path,
                "chunk_level": chunk.chunk_level,
                "parent_id": self._parent_id(chunk, chunk_ids[index], parent_ids),
                "parent_article_number": chunk.parent_article_number,
                "article_number": chunk.article_number,
                "clause_number": chunk.clause_number,
                "point_number": chunk.point_number,
                "child_text": chunk.child_text,
                "parent_text": chunk.parent_text,
                "chunking_strategy": chunk.chunking_strategy,
                "title": document.get("title"),
                "document_number": document.get("documentNumber"),
                "document_type": document.get("documentType"),
                "validity_status": document.get("validityStatus"),
                "issued_date": document.get("issuedDate"),
                "effective_date": document.get("effectiveDate"),
                "expired_date": document.get("expiredDate"),
                "issuing_authority": document.get("issuingAuthority"),
                "scope": document.get("scope"),
                "source": document.get("source"),
                "source_url": document.get("sourceUrl"),
                "external_source": document.get("externalSource"),
                "external_docid": document.get("externalDocid"),
            }
            for index, chunk in enumerate(chunks)
        ]
        vectors = self.embedding_model.embed([chunk.retrieval_text for chunk in chunks])
        return self.vector_store.replace_document_chunks(
            document_id,
            payloads,
            vectors,
            delete_existing=self.settings.qdrant_delete_existing_chunks,
        )

    @staticmethod
    def _document_context(document: dict) -> str:
        fields = [
            ("Tiêu đề", document.get("title")),
            ("Số/Ký hiệu", document.get("documentNumber")),
            ("Loại văn bản", document.get("documentType")),
            ("Tình trạng hiệu lực", document.get("validityStatus")),
            ("Ngày ban hành", document.get("issuedDate")),
            ("Ngày hiệu lực", document.get("effectiveDate")),
            ("Ngày hết hiệu lực", document.get("expiredDate")),
            ("Cơ quan ban hành", document.get("issuingAuthority")),
            ("Phạm vi", document.get("scope")),
            ("Nguồn", document.get("source")),
            ("URL nguồn", document.get("sourceUrl")),
            ("Mã nguồn ngoài", document.get("externalDocid")),
        ]
        return "\n".join(f"{label}: {value}" for label, value in fields if value)

    @staticmethod
    def _parent_id(chunk, chunk_id: str, parent_ids: dict[str, str]) -> str | None:
        if chunk.parent_id:
            return chunk.parent_id
        if chunk.chunk_level == "parent" and chunk.parent_key:
            return chunk_id
        if chunk.parent_key:
            return parent_ids.get(chunk.parent_key)
        return None
