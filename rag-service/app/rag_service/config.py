from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "rag-service"
    environment: str = "local"
    log_level: str = "INFO"

    law_service_base_url: AnyHttpUrl = "http://localhost:8080"

    qdrant_url: AnyHttpUrl = "http://localhost:6333"
    qdrant_collection: str = "legal_document_chunks"
    qdrant_delete_existing_chunks: bool = False
    qdrant_timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    qdrant_upsert_batch_size: int = Field(default=64, ge=1, le=512)

    redis_url: str = "redis://localhost:6379/1"
    celery_broker_url: str = "redis://localhost:6379/2"
    celery_result_backend: str = "redis://localhost:6379/3"

    rabbitmq_url: str = "amqp://law:law@localhost:5672/"
    rabbitmq_embedding_queue: str = "law.embedding.update"

    answer_language: str = "Vietnamese"

    embedding_model_name: str = "mainguyen9/vietlegal-harrier-0.6b"
    embedding_dimension: int = 1024
    embedding_query_instruction: str = (
        "Instruct: Given a Vietnamese legal question, retrieve relevant legal passages "
        "that answer the question\nQuery: "
    )
    embedding_device: str = "cpu"
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    embedding_local_files_only: bool = False
    reranker_model_name: str = "kiencnt2205/vietnamese-legal-reranker-bge-base"
    enable_reranker: bool = True

    chunk_size: int = Field(default=1500, ge=200, le=4000)
    chunk_overlap: int = Field(default=200, ge=0, le=1000)
    retrieval_limit: int = Field(default=40, ge=1, le=200)
    rerank_limit: int = Field(default=8, ge=1, le=50)

    llm_provider: str = "stub"
    llm_api_type: str = "chat_completions"
    llm_api_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = "luanngo/Qwen3-4B-VietNamese-Legal-Chat"
    llm_reasoning_effort: str | None = None
    llm_max_output_tokens: int = Field(default=4096, ge=256, le=128000)

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
