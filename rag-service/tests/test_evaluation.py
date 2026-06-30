import asyncio
import json
from argparse import Namespace

import httpx
from rag_service.evaluation import (
    citation_coverage,
    duplicate_document_rate,
    judge_result,
    load_questions,
    parse_judge_scores,
    recall_at_k,
    retrieval_cutoff_violation_count,
    top1_gold_hit,
    warn_if_judge_endpoint_looks_local,
)


def test_citation_coverage_counts_valid_reference_indexes() -> None:
    cited_count, coverage = citation_coverage("Câu trả lời [1], [3], [9].", reference_count=3)

    assert cited_count == 2
    assert coverage == 2 / 3


def test_parse_judge_scores_json() -> None:
    scores = parse_judge_scores(
        '{"retrieval_relevance": 80, "answer_groundedness": "90", '
        '"citation_quality": 70, "legal_usefulness": 85, "notes": "ổn"}'
    )

    assert scores.retrieval_relevance == 80
    assert scores.answer_groundedness == 90
    assert scores.citation_quality == 70
    assert scores.legal_usefulness == 85
    assert scores.notes == "ổn"


def test_load_questions_normalizes_retrieval_cutoff_date(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "question": "Câu hỏi?",
                    "published_date": "06/03/2025",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    case = load_questions(str(path), url=None, limit=None)[0]

    assert case.question_date == "2025-03-06"
    assert case.retrieval_cutoff_date == "2025-03-06"


def test_load_questions_accepts_gold_retrieval_labels(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "question": "Câu hỏi?",
                    "gold_document_ids": ["42", 84],
                    "gold_chunk_ids": ["42:1", 84],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    case = load_questions(str(path), url=None, limit=None)[0]

    assert case.gold_document_ids == [42, 84]
    assert case.gold_chunk_ids == ["42:1", "84"]


def test_load_questions_derives_gold_document_ids_from_expected_citations(tmp_path) -> None:
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            [
                {
                    "question": "Câu hỏi?",
                    "expected_legal_citations": [
                        {"document_id": "42"},
                        {"document_id": 42},
                        {"document_id": 84},
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    case = load_questions(str(path), url=None, limit=None)[0]

    assert case.gold_document_ids == [42, 84]


def test_recall_at_k_returns_none_without_gold_labels() -> None:
    assert recall_at_k([1, 2, 3], None) is None
    assert recall_at_k([1, 2, 3], []) is None


def test_recall_at_k_scores_gold_overlap() -> None:
    assert recall_at_k([1, 3, 5], [1, 2, 3, 4]) == 0.5


def test_top1_gold_hit_scores_first_document_only() -> None:
    assert top1_gold_hit([1, 2, 3], [2, 3]) is False
    assert top1_gold_hit([2, 1, 3], [2, 3]) is True
    assert top1_gold_hit([2, 1, 3], None) is None


def test_duplicate_document_rate_counts_repeated_documents() -> None:
    assert duplicate_document_rate([10, 10, 20, 20, 20]) == 0.6
    assert duplicate_document_rate([]) == 0.0


def test_retrieval_cutoff_violation_count_counts_future_documents() -> None:
    references = [
        {"document_id": 1, "issued_date": "2025-01-01"},
        {"document_id": 2, "issued_date": "2025-01-02"},
        {"document_id": 3, "issued_date": None},
    ]

    assert retrieval_cutoff_violation_count(references, "2025-01-01") == 1
    assert retrieval_cutoff_violation_count(references, None) == 0


def test_judge_result_records_http_failures() -> None:
    class FailingJudgeClient:
        async def generate(self, _prompt: str) -> str:
            raise httpx.ConnectError("All connection attempts failed")

    scores = asyncio.run(
        judge_result(
            True,
            FailingJudgeClient(),
            "Câu hỏi?",
            "Trả lời [1]",
            [{"document_id": 1, "title": "Văn bản", "text": "Nội dung"}],
            "Đáp án",
        )
    )

    assert scores.retrieval_relevance is None
    assert scores.notes == "Judge failed: ConnectError: All connection attempts failed"


def test_warn_if_judge_endpoint_looks_local(capsys) -> None:
    warn_if_judge_endpoint_looks_local(
        Namespace(
            judge_provider="openai-compatible",
            judge_api_base_url="http://localhost:8000/v1",
        )
    )

    assert "judge API base URL is local" in capsys.readouterr().err
