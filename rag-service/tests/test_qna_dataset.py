import pandas as pd
from rag_service.models import SourceReference
from rag_service.qna_dataset import (
    ExpectedCitation,
    citation_matches_reference,
    load_qna_benchmark,
)


def test_load_qna_benchmark_groups_citations_by_question(tmp_path) -> None:
    dataset_dir = tmp_path
    pd.DataFrame(
        [
            {
                "qna_id": 1,
                "question": "Câu hỏi?",
                "reference_answer": "Trả lời.",
                "published_date": "2026-01-01",
                "citation_id": 10,
                "expected_document_id": 42,
                "expected_document_number": "01/2026/QH",
                "article_refs": "Điều 8",
                "clause_refs": "khoản 2",
                "point_refs": "điểm b",
                "cited_text": "Điều 8 khoản 2 điểm b",
            },
            {
                "qna_id": 1,
                "question": "Câu hỏi?",
                "reference_answer": "Trả lời.",
                "published_date": "2026-01-01",
                "citation_id": 11,
                "expected_document_id": 43,
                "expected_document_number": "02/2026/NĐ-CP",
                "article_refs": None,
                "clause_refs": None,
                "point_refs": None,
                "cited_text": "Nghị định khác",
            },
        ]
    ).to_parquet(dataset_dir / "government_qna_benchmark.parquet")

    items = load_qna_benchmark(dataset_dir)

    assert len(items) == 1
    assert items[0].qna_id == 1
    assert len(items[0].citations) == 2
    assert items[0].citations[0].article_numbers == ("8",)
    assert items[0].citations[0].clause_numbers == ("2",)
    assert items[0].citations[0].point_numbers == ("b",)


def test_citation_match_requires_requested_structure() -> None:
    citation = ExpectedCitation(
        citation_id=1,
        document_id=42,
        document_number="01/2026/QH",
        article_numbers=("8",),
        clause_numbers=("2",),
        point_numbers=("b",),
    )
    reference = SourceReference(
        document_id=42,
        chunk_id="42:8",
        article_number="8",
        clause_number="2",
        point_number="b",
        score=1,
        text="Điều 8 khoản 2 điểm b",
    )
    wrong_clause = reference.model_copy(
        update={"clause_number": "3", "text": "Điều 8 khoản 3 điểm b"}
    )

    assert citation_matches_reference(reference, citation) is True
    assert citation_matches_reference(wrong_clause, citation) is False
