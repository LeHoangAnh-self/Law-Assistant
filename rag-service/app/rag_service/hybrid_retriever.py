from __future__ import annotations

from datetime import date

from rag_service.models import SourceReference
from rag_service.retrieval import (
    DenseRetriever,
    LexicalRetriever,
    RetrievalQuery,
    exact_match_boost,
)


class HybridRetriever:
    def __init__(
        self,
        dense_retriever: DenseRetriever,
        lexical_retriever: LexicalRetriever,
        *,
        dense_limit: int = 50,
        lexical_limit: int = 50,
        dense_weight: float = 0.6,
        lexical_weight: float = 0.4,
    ) -> None:
        self.dense_retriever = dense_retriever
        self.lexical_retriever = lexical_retriever
        self.dense_limit = dense_limit
        self.lexical_limit = lexical_limit
        self.dense_weight = dense_weight
        self.lexical_weight = lexical_weight

    def retrieve(
        self,
        query: RetrievalQuery,
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        dense_hits = self.dense_retriever.retrieve(
            query,
            limit=self.dense_limit,
            filters=filters or {},
            issued_date_lte=issued_date_lte,
        )
        lexical_hits = self.lexical_retriever.retrieve(
            query.text,
            limit=self.lexical_limit,
            filters=filters or {},
            issued_date_lte=issued_date_lte,
        )
        dense_norms = self._normalized_scores(
            {
                reference.chunk_id: self._score_value(reference.dense_score, reference.score)
                for reference in dense_hits
            }
        )
        lexical_norms = self._normalized_scores(
            {
                reference.chunk_id: self._score_value(reference.bm25_score, reference.score)
                for reference in lexical_hits
            }
        )

        merged: dict[str, SourceReference] = {}
        for reference in dense_hits + lexical_hits:
            previous = merged.get(reference.chunk_id)
            if previous is None:
                merged[reference.chunk_id] = reference
                continue
            merged[reference.chunk_id] = self._merge_reference(previous, reference)

        rescored = []
        for chunk_id, reference in merged.items():
            dense_score = reference.dense_score
            bm25_score = reference.bm25_score
            boost = exact_match_boost(query.text, reference)
            hybrid_score = (
                self.dense_weight * dense_norms.get(chunk_id, 0.0)
                + self.lexical_weight * lexical_norms.get(chunk_id, 0.0)
                + boost
            )
            rescored.append(
                reference.model_copy(
                    update={
                        "dense_score": dense_score,
                        "bm25_score": bm25_score,
                        "exact_match_boost": boost,
                        "hybrid_score": hybrid_score,
                        "score": hybrid_score,
                    }
                )
            )
        rescored.sort(
            key=lambda reference: reference.hybrid_score or reference.score,
            reverse=True,
        )
        return rescored[:limit]

    @staticmethod
    def _merge_reference(left: SourceReference, right: SourceReference) -> SourceReference:
        dense_score = left.dense_score
        if right.dense_score is not None and (
            dense_score is None or right.dense_score > dense_score
        ):
            dense_score = right.dense_score
        bm25_score = left.bm25_score
        if right.bm25_score is not None and (
            bm25_score is None or right.bm25_score > bm25_score
        ):
            bm25_score = right.bm25_score
        base = left if left.score >= right.score else right
        return base.model_copy(update={"dense_score": dense_score, "bm25_score": bm25_score})

    @staticmethod
    def _score_value(primary: float | None, fallback: float) -> float:
        return primary if primary is not None else fallback

    @staticmethod
    def _normalized_scores(scores: dict[str, float | None]) -> dict[str, float]:
        present = {key: value for key, value in scores.items() if value is not None}
        if not present:
            return {}
        maximum = max(present.values())
        minimum = min(present.values())
        if maximum == minimum:
            return {key: 1.0 for key in present}
        return {
            key: (value - minimum) / (maximum - minimum)
            for key, value in present.items()
        }
