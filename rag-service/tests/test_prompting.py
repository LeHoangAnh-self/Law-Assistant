from rag_service.models import SourceReference
from rag_service.prompting import build_legal_prompt


def test_prompt_contains_question_and_citations() -> None:
    prompt = build_legal_prompt(
        "Văn bản này còn hiệu lực không?",
        [
            SourceReference(
                document_id=42,
                chunk_id="42:0",
                title="Một văn bản luật",
                document_number="LAW-42",
                source="source-url",
                issued_date="2026-01-01",
                score=0.9,
                text="Văn bản này còn hiệu lực.",
            )
        ],
    )

    assert "Văn bản này còn hiệu lực không?" in prompt
    assert "[1] Văn bản 42" in prompt
    assert "Văn bản này còn hiệu lực." in prompt
