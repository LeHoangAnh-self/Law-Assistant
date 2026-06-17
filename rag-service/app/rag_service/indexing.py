from rag_service.chunking import chunk_text
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
        )

    def index_document(self, document_id: int) -> int:
        detail = self.law_client.get_document_detail_sync(document_id)
        document = detail["document"]
        text = detail.get("contentText") or document.get("title") or ""
        chunks = chunk_text(text, self.settings.chunk_size, self.settings.chunk_overlap)
        payloads = [
            {
                "chunk_id": f"{document_id}:{index}",
                "document_id": document_id,
                "chunk_index": index,
                "text": chunk,
                "title": document.get("title"),
                "document_number": document.get("documentNumber"),
                "document_type": document.get("documentType"),
                "validity_status": document.get("validityStatus"),
                "issued_date": document.get("issuedDate"),
                "source": document.get("source"),
            }
            for index, chunk in enumerate(chunks)
        ]
        vectors = self.embedding_model.embed(chunks)
        return self.vector_store.replace_document_chunks(
            document_id,
            payloads,
            vectors,
            delete_existing=self.settings.qdrant_delete_existing_chunks,
        )
