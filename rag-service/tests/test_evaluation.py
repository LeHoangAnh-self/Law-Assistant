import json

from rag_service.evaluation import citation_coverage, load_questions, parse_judge_scores


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
