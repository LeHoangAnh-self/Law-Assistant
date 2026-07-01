from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from rag_service.models import SourceReference
from rag_service.retrieval import LexicalRetriever

TOKEN_RE = re.compile(r"[0-9a-zA-ZÀ-ỹĐđ/.-]+")
CorpusCacheValue = tuple[list["Bm25Document"], dict[str, int], float]

FIELD_WEIGHTS = {
    "document_number": 4,
    "article_number": 3,
    "clause_number": 3,
    "legal_path": 3,
    "title": 2,
    "retrieval_text": 1,
    "text": 1,
}


@dataclass(frozen=True)
class Bm25Document:
    reference: SourceReference
    term_counts: Counter[str]
    length: int


class BM25Retriever(LexicalRetriever):
    def __init__(
        self,
        vector_store,
        *,
        corpus_limit: int = 200000,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.vector_store = vector_store
        self.corpus_limit = corpus_limit
        self.k1 = k1
        self.b = b
        self._cache: dict[tuple[tuple[tuple[str, str], ...], str | None], CorpusCacheValue] = {}

    def retrieve(
        self,
        query: str,
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []
        documents, doc_freqs, average_length = self._corpus(filters or {}, issued_date_lte)
        if not documents:
            return []

        query_counts = Counter(query_terms)
        scored: list[tuple[float, SourceReference]] = []
        document_count = len(documents)
        for document in documents:
            score = 0.0
            for term, query_frequency in query_counts.items():
                term_frequency = document.term_counts.get(term, 0)
                if not term_frequency:
                    continue
                doc_frequency = doc_freqs.get(term, 0)
                idf = math.log(1 + (document_count - doc_frequency + 0.5) / (doc_frequency + 0.5))
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * document.length / average_length
                )
                score += query_frequency * idf * (term_frequency * (self.k1 + 1) / denominator)
            if score > 0:
                scored.append(
                    (
                        score,
                        document.reference.model_copy(update={"bm25_score": score, "score": score}),
                    )
                )

        scored.sort(key=lambda item: item[0], reverse=True)
        return [reference for _, reference in scored[:limit]]

    def _corpus(
        self,
        filters: dict[str, str],
        issued_date_lte: date | None,
    ) -> tuple[list[Bm25Document], dict[str, int], float]:
        cache_key = (
            tuple(sorted((key, str(value)) for key, value in filters.items())),
            issued_date_lte.isoformat() if issued_date_lte else None,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        if not hasattr(self.vector_store, "scroll_references"):
            return [], {}, 1.0

        references = self.vector_store.scroll_references(
            limit=self.corpus_limit,
            issued_date_lte=issued_date_lte,
            filters=filters,
        )
        documents = [self._build_document(reference) for reference in references]
        documents = [document for document in documents if document.length > 0]
        doc_freqs: dict[str, int] = {}
        for document in documents:
            for term in document.term_counts:
                doc_freqs[term] = doc_freqs.get(term, 0) + 1
        average_length = sum(document.length for document in documents) / max(1, len(documents))
        corpus = (documents, doc_freqs, max(1.0, average_length))
        self._cache[cache_key] = corpus
        return corpus

    @classmethod
    def _build_document(cls, reference: SourceReference) -> Bm25Document:
        terms: list[str] = []
        for field, weight in FIELD_WEIGHTS.items():
            value = getattr(reference, field, None)
            if value is None:
                continue
            field_terms = cls._tokenize(str(value))
            for _ in range(weight):
                terms.extend(field_terms)
        return Bm25Document(reference=reference, term_counts=Counter(terms), length=len(terms))

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]
