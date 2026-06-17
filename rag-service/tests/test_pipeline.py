import asyncio

from rag_service.config import Settings
from rag_service.models import AskRequest
from rag_service.pipeline import RagPipeline


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.seen_text: str | None = None

    def embed_one(self, text: str) -> list[float]:
        self.seen_text = text
        return [0.1, 0.2]


class FakeVectorStore:
    def __init__(self) -> None:
        self.issued_date_lte = None

    def search(
        self,
        _vector: list[float],
        limit: int,
        filters: dict[str, str],
        issued_date_lte=None,
    ):
        assert limit == 40
        assert filters == {}
        self.issued_date_lte = issued_date_lte
        return []


class FakeReranker:
    def rerank(self, _query: str, references: list, limit: int):
        assert limit == 5
        return references


class FakeLlmClient:
    async def generate(self, _prompt: str) -> str:
        return "answer"


def test_pipeline_prefixes_query_with_embedding_instruction() -> None:
    embedding_model = FakeEmbeddingModel()
    settings = Settings(
        embedding_query_instruction="Instruct: test\nQuery: ",
        embedding_dimension=2,
    )
    pipeline = RagPipeline(
        settings,
        embedding_model=embedding_model,
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="  Văn bản nào còn hiệu lực?  ", top_k=5))
    )

    assert embedding_model.seen_text == "Instruct: test\nQuery: Văn bản nào còn hiệu lực?"
    assert response.answer == "answer"


def test_pipeline_passes_retrieval_cutoff_to_vector_store() -> None:
    vector_store = FakeVectorStore()
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=FakeEmbeddingModel(),
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    asyncio.run(
        pipeline.ask(
            AskRequest(
                question="Quy định nào áp dụng?",
                top_k=5,
                retrieval_cutoff_date="2025-03-06",
            )
        )
    )

    assert vector_store.issued_date_lte.isoformat() == "2025-03-06"
