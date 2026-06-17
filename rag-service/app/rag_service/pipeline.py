from rag_service.config import Settings
from rag_service.embedding import EmbeddingModel
from rag_service.llm import LlmClient
from rag_service.models import AskRequest, AskResponse
from rag_service.prompting import build_legal_prompt
from rag_service.reranking import CrossEncoderReranker
from rag_service.vector_store import QdrantVectorStore


class RagPipeline:
    def __init__(
        self,
        settings: Settings,
        embedding_model: EmbeddingModel | None = None,
        vector_store: QdrantVectorStore | None = None,
        reranker: CrossEncoderReranker | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self.settings = settings
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
        self.reranker = reranker or CrossEncoderReranker(
            settings.reranker_model_name,
            settings.enable_reranker,
        )
        self.llm_client = llm_client or LlmClient(
            provider=settings.llm_provider,
            api_base_url=settings.llm_api_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

    async def ask(self, request: AskRequest) -> AskResponse:
        rewritten_query = self._rewrite_query(request.question)
        classification = self._classify_question(rewritten_query)
        embedding_query = f"{self.settings.embedding_query_instruction}{rewritten_query}"
        query_vector = self.embedding_model.embed_one(embedding_query)
        candidates = self.vector_store.search(
            query_vector,
            limit=self.settings.retrieval_limit,
            filters=request.filters,
            issued_date_lte=request.retrieval_cutoff_date,
        )
        references = self.reranker.rerank(rewritten_query, candidates, limit=request.top_k)
        prompt = build_legal_prompt(
            request.question,
            references,
            answer_language=self.settings.answer_language,
        )
        answer = await self.llm_client.generate(prompt)
        return AskResponse(
            answer=answer,
            rewritten_query=rewritten_query,
            classification=classification,
            references=references,
        )

    @staticmethod
    def _rewrite_query(question: str) -> str:
        return " ".join(question.strip().split())

    @staticmethod
    def _classify_question(question: str) -> str:
        lowered = question.lower()
        if any(
            term in lowered
            for term in ["expire", "valid", "effective", "hiệu lực", "hết hiệu lực", "còn hiệu lực"]
        ):
            return "validity"
        if any(
            term in lowered
            for term in ["amend", "replace", "relationship", "sửa đổi", "thay thế", "bổ sung"]
        ):
            return "relationship"
        return "legal_research"
