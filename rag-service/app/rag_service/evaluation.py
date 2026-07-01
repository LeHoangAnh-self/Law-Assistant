from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from rag_service.config import Settings
from rag_service.embedding import EmbeddingModel
from rag_service.qna_dataset import (
    QnaBenchmarkItem,
    citation_matches_reference,
    document_matches_reference,
    load_qna_benchmark,
    reference_training_text,
    write_qwen_reranker_jsonl,
)
from rag_service.reranking import CrossEncoderReranker
from rag_service.vector_store import QdrantVectorStore


@dataclass(frozen=True)
class EvalConfig:
    dataset_dir: Path
    limit: int | None = None
    candidate_k: int = 40
    rerank_k: int = 10
    output_json: Path | None = None
    training_jsonl: Path | None = None


@dataclass(frozen=True)
class EvalSummary:
    question_count: int
    citation_count: int
    candidate_k: int
    rerank_k: int
    document_recall_at_candidate_k: float
    citation_recall_at_candidate_k: float
    document_mrr_at_k: float
    citation_mrr_at_k: float
    document_ndcg_at_k: float
    citation_ndcg_at_k: float
    exact_citation_hit_at_k: float
    avg_retrieval_latency_ms: float
    avg_rerank_latency_ms: float
    training_rows_written: int = 0


class QnaRerankerEvaluator:
    def __init__(
        self,
        settings: Settings,
        *,
        embedding_model: EmbeddingModel | None = None,
        vector_store: QdrantVectorStore | None = None,
        reranker: CrossEncoderReranker | None = None,
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
            timeout=settings.qdrant_timeout_seconds,
            upsert_batch_size=settings.qdrant_upsert_batch_size,
        )
        self.reranker = reranker or CrossEncoderReranker(
            settings.reranker_model_name,
            settings.enable_reranker,
            query_instruction=settings.reranker_query_instruction,
        )

    def evaluate(self, config: EvalConfig) -> EvalSummary:
        items = load_qna_benchmark(config.dataset_dir, limit=config.limit)
        if not items:
            raise ValueError(f"No benchmark rows found under {config.dataset_dir}")

        retrieval_latencies: list[float] = []
        rerank_latencies: list[float] = []
        document_recall_hits = 0
        citation_recall_hits = 0
        document_rr_total = 0.0
        citation_rr_total = 0.0
        document_ndcg_total = 0.0
        citation_ndcg_total = 0.0
        citation_hit_at_k = 0
        citation_count = 0
        training_rows: list[dict] = []

        for item in items:
            retrieval_start = time.perf_counter()
            candidates = self._retrieve_candidates(item, config.candidate_k)
            retrieval_latencies.append((time.perf_counter() - retrieval_start) * 1000)

            rerank_start = time.perf_counter()
            ranked = self.reranker.rerank(item.question, candidates, limit=config.candidate_k)
            rerank_latencies.append((time.perf_counter() - rerank_start) * 1000)
            top_ranked = ranked[: config.rerank_k]

            for citation in item.citations:
                citation_count += 1
                candidate_doc_ranks = [
                    index
                    for index, reference in enumerate(candidates, start=1)
                    if document_matches_reference(reference, citation)
                ]
                candidate_citation_ranks = [
                    index
                    for index, reference in enumerate(candidates, start=1)
                    if citation_matches_reference(reference, citation)
                ]
                if candidate_doc_ranks:
                    document_recall_hits += 1
                if candidate_citation_ranks:
                    citation_recall_hits += 1

                doc_ranks = [
                    index
                    for index, reference in enumerate(top_ranked, start=1)
                    if document_matches_reference(reference, citation)
                ]
                citation_ranks = [
                    index
                    for index, reference in enumerate(top_ranked, start=1)
                    if citation_matches_reference(reference, citation)
                ]
                document_rr_total += _reciprocal_rank(doc_ranks)
                citation_rr_total += _reciprocal_rank(citation_ranks)
                document_ndcg_total += _ndcg(doc_ranks)
                citation_ndcg_total += _ndcg(citation_ranks)
                if citation_ranks:
                    citation_hit_at_k += 1

            if config.training_jsonl:
                training_rows.extend(_training_rows_for_item(item, ranked))

        training_rows_written = 0
        if config.training_jsonl:
            training_rows_written = write_qwen_reranker_jsonl(training_rows, config.training_jsonl)

        summary = EvalSummary(
            question_count=len(items),
            citation_count=citation_count,
            candidate_k=config.candidate_k,
            rerank_k=config.rerank_k,
            document_recall_at_candidate_k=document_recall_hits / citation_count,
            citation_recall_at_candidate_k=citation_recall_hits / citation_count,
            document_mrr_at_k=document_rr_total / citation_count,
            citation_mrr_at_k=citation_rr_total / citation_count,
            document_ndcg_at_k=document_ndcg_total / citation_count,
            citation_ndcg_at_k=citation_ndcg_total / citation_count,
            exact_citation_hit_at_k=citation_hit_at_k / citation_count,
            avg_retrieval_latency_ms=sum(retrieval_latencies) / len(retrieval_latencies),
            avg_rerank_latency_ms=sum(rerank_latencies) / len(rerank_latencies),
            training_rows_written=training_rows_written,
        )
        if config.output_json:
            config.output_json.parent.mkdir(parents=True, exist_ok=True)
            config.output_json.write_text(
                json.dumps(asdict(summary), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return summary

    def _retrieve_candidates(self, item: QnaBenchmarkItem, candidate_k: int):
        embedding_query = f"{self.settings.embedding_query_instruction}{item.question}"
        query_vector = self.embedding_model.embed_one(embedding_query)
        return self.vector_store.search(
            query_vector,
            limit=candidate_k,
            filters={},
            issued_date_lte=None,
        )


def _training_rows_for_item(item: QnaBenchmarkItem, ranked) -> list[dict]:
    positives = [
        reference
        for reference in ranked
        if any(citation_matches_reference(reference, citation) for citation in item.citations)
    ]
    negatives = [
        reference
        for reference in ranked
        if not any(document_matches_reference(reference, citation) for citation in item.citations)
    ]
    rows = []
    for positive in positives[:3]:
        rows.append(
            {
                "query": item.question,
                "pos": [reference_training_text(positive)],
                "neg": [reference_training_text(reference) for reference in negatives[:8]],
                "prompt": (
                    "Given a Vietnamese legal question, retrieve relevant legal passages "
                    "that answer the question"
                ),
                "qna_id": item.qna_id,
                "positive_chunk_id": positive.chunk_id,
                "positive_document_id": positive.document_id,
            }
        )
    return rows


def _reciprocal_rank(ranks: list[int]) -> float:
    return 0.0 if not ranks else 1.0 / min(ranks)


def _ndcg(ranks: list[int]) -> float:
    if not ranks:
        return 0.0
    return 1.0 / math.log2(min(ranks) + 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate LawAssistant reranking on Q&A citations."
    )
    parser.add_argument(
        "--dataset-dir",
        default="/home/lee/Documents/LawAssistant/data_usable/government_qna",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--candidate-k", type=int, default=40)
    parser.add_argument("--rerank-k", type=int, default=10)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--training-jsonl", default=None)
    args = parser.parse_args()

    settings = Settings()
    evaluator = QnaRerankerEvaluator(settings)
    summary = evaluator.evaluate(
        EvalConfig(
            dataset_dir=Path(args.dataset_dir),
            limit=args.limit,
            candidate_k=args.candidate_k,
            rerank_k=args.rerank_k,
            output_json=Path(args.output_json) if args.output_json else None,
            training_jsonl=Path(args.training_jsonl) if args.training_jsonl else None,
        )
    )
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
