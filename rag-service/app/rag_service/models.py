from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=20)
    filters: dict[str, str] = Field(default_factory=dict)
    retrieval_cutoff_date: date | None = None
    conversation_context: str | None = Field(default=None, max_length=4000)


class SourceReference(BaseModel):
    document_id: int
    chunk_id: str
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    validity_status: str | None = None
    source: str | None = None
    source_url: str | None = None
    external_source: str | None = None
    external_docid: str | None = None
    issued_date: str | None = None
    effective_date: str | None = None
    expired_date: str | None = None
    issuing_authority: str | None = None
    scope: str | None = None
    legal_path: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_number: str | None = None
    chunking_strategy: str | None = None
    score: float
    text: str


class AskResponse(BaseModel):
    answer: str
    rewritten_query: str
    classification: str
    references: list[SourceReference]
    retrieval_query: str | None = None
    retrieval_diagnostics: dict[str, object] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str


class EmbeddingUpdateEvent(BaseModel):
    documentId: int
    reason: str | None = None
    requestedAt: datetime | None = None

    @field_validator("requestedAt", mode="before")
    @classmethod
    def parse_requested_at(cls, value: Any) -> Any:
        if isinstance(value, int | float):
            return datetime.fromtimestamp(value, tz=UTC)
        return value
