from pathlib import Path

import pandas as pd
from rag_service.config import Settings
from rag_service.evaluation import EvalConfig, QnaRerankerEvaluator
from rag_service.models import SourceReference


class FakeEmbeddingModel:
    def embed_one(self, text: str) -> list[float]:
        assert "Câu hỏi pháp lý?" in text
        return [0.1, 0.2]


class FakeVectorStore:
    def search(self, _vector, limit, filters, issued_date_lte=None):
        assert limit == 3
        assert filters == {}
        assert issued_date_lte is None
        return [
            SourceReference(document_id=1, chunk_id="1:1", score=0.9, text="Sai"),
            SourceReference(
                document_id=42,
                chunk_id="42:8",
                article_number="8",
                score=0.8,
                text="Điều 8 đúng",
                retrieval_text="Tiêu đề: Luật đúng\nĐiều 8 đúng",
            ),
            SourceReference(document_id=99, chunk_id="99:1", score=0.7, text="Sai khác"),
        ]


class FakeReranker:
    def rerank(self, _query, references, limit):
        assert limit == 3
        return [references[1], references[0], references[2]]


def write_benchmark(dataset_dir: Path) -> None:
    pd.DataFrame(
        [
            {
                "qna_id": 1,
                "question": "Câu hỏi pháp lý?",
                "reference_answer": "Trả lời.",
                "published_date": "2026-01-01",
                "citation_id": 10,
                "expected_document_id": 42,
                "expected_document_number": "01/2026/QH",
                "article_refs": "Điều 8",
                "clause_refs": None,
                "point_refs": None,
                "cited_text": "Điều 8",
            }
        ]
    ).to_parquet(dataset_dir / "government_qna_benchmark.parquet")


def test_qna_reranker_evaluator_reports_recall_and_rerank_metrics(tmp_path) -> None:
    write_benchmark(tmp_path)
    output_json = tmp_path / "summary.json"
    training_jsonl = tmp_path / "training.jsonl"
    evaluator = QnaRerankerEvaluator(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
    )

    summary = evaluator.evaluate(
        EvalConfig(
            dataset_dir=tmp_path,
            candidate_k=3,
            rerank_k=2,
            output_json=output_json,
            training_jsonl=training_jsonl,
        )
    )

    assert summary.question_count == 1
    assert summary.citation_count == 1
    assert summary.document_recall_at_candidate_k == 1.0
    assert summary.citation_recall_at_candidate_k == 1.0
    assert summary.document_mrr_at_k == 1.0
    assert summary.citation_mrr_at_k == 1.0
    assert summary.exact_citation_hit_at_k == 1.0
    assert summary.training_rows_written == 1
    assert output_json.exists()
    assert '"positive_chunk_id": "42:8"' in training_jsonl.read_text(encoding="utf-8")
