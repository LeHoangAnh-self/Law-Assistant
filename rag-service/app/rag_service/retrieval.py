from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from rag_service.embedding import EmbeddingModel
from rag_service.models import SourceReference
from rag_service.vector_store import QdrantVectorStore

DOCUMENT_NUMBER_RE = re.compile(
    r"\b\d{1,4}/\d{4}/[A-ZĐÂÊÔƠƯ0-9.-]+(?:-[A-ZĐÂÊÔƠƯ0-9.-]+)*\b",
    re.IGNORECASE,
)
ARTICLE_REF_RE = re.compile(r"\bđiều\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
CLAUSE_REF_RE = re.compile(r"\bkhoản\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
POINT_REF_RE = re.compile(r"\bđiểm\s+(?P<number>[a-zđ])\b", re.IGNORECASE)


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    embedding_text: str | None = None
    vector: list[float] | None = None


class DenseRetriever(ABC):
    @abstractmethod
    def retrieve(
        self,
        query: RetrievalQuery,
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        raise NotImplementedError


class LexicalRetriever(ABC):
    @abstractmethod
    def retrieve(
        self,
        query: str,
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        raise NotImplementedError


class QdrantDenseRetriever(DenseRetriever):
    def __init__(self, vector_store: QdrantVectorStore, embedding_model: EmbeddingModel) -> None:
        self.vector_store = vector_store
        self.embedding_model = embedding_model

    def retrieve(
        self,
        query: RetrievalQuery,
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        vector = query.vector
        if vector is None:
            if not query.embedding_text:
                msg = "Dense retrieval requires either a vector or embedding text."
                raise ValueError(msg)
            vector = self.embedding_model.embed_one(query.embedding_text)
        hits = self.vector_store.search(
            vector,
            limit=limit,
            filters=filters or {},
            issued_date_lte=issued_date_lte,
        )
        return [hit.model_copy(update={"dense_score": hit.score}) for hit in hits]


def normalize_identifier(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip(".,;:)").upper()


def normalize_ref_number(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip(".,;:)").lower()


def normalize_point_label(value: str | None) -> str:
    return (value or "").strip().lower()


def query_exact_references(query: str) -> dict[str, tuple[str, ...]]:
    return {
        "document_numbers": tuple(
            dict.fromkeys(
                normalize_identifier(match.group(0))
                for match in DOCUMENT_NUMBER_RE.finditer(query)
            )
        ),
        "article_numbers": tuple(
            dict.fromkeys(
                normalize_ref_number(match.group("number"))
                for match in ARTICLE_REF_RE.finditer(query)
            )
        ),
        "clause_numbers": tuple(
            dict.fromkeys(
                normalize_ref_number(match.group("number"))
                for match in CLAUSE_REF_RE.finditer(query)
            )
        ),
        "point_numbers": tuple(
            dict.fromkeys(
                normalize_point_label(match.group("number"))
                for match in POINT_REF_RE.finditer(query)
            )
        ),
    }


def reference_haystack(reference: SourceReference) -> str:
    return " ".join(
        value or ""
        for value in [
            reference.title,
            reference.document_number,
            reference.legal_path,
            reference.article_number,
            reference.clause_number,
            reference.point_number,
            reference.retrieval_text,
            reference.text,
        ]
    ).lower()


def exact_match_boost(query: str, reference: SourceReference) -> float:
    refs = query_exact_references(query)
    haystack = reference_haystack(reference)
    boost = 0.0

    reference_document_number = normalize_identifier(reference.document_number)
    if reference_document_number and reference_document_number in refs["document_numbers"]:
        boost += 3.0
    for document_number in refs["document_numbers"]:
        if document_number.lower() in haystack:
            boost += 1.5
            break

    reference_article = normalize_ref_number(
        reference.article_number or reference.parent_article_number
    )
    for article_number in refs["article_numbers"]:
        if reference_article == article_number or f"điều {article_number}" in haystack:
            boost += 2.5
            break

    reference_clause = normalize_ref_number(reference.clause_number)
    for clause_number in refs["clause_numbers"]:
        if reference_clause == clause_number or f"khoản {clause_number}" in haystack:
            boost += 1.5
            break

    reference_point = normalize_point_label(reference.point_number)
    for point_number in refs["point_numbers"]:
        if reference_point == point_number or f"điểm {point_number}" in haystack:
            boost += 1.0
            break

    return boost
