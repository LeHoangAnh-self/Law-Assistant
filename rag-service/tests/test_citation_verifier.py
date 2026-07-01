from rag_service.citation_verifier import EXAMPLE_VERIFIER_OUTPUT, verify_citations
from rag_service.models import SourceReference


def labor_reference() -> SourceReference:
    return SourceReference(
        document_id=139264,
        chunk_id="139264:25",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        article_number="35",
        legal_path="Chương III > Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động",
        score=10,
        text=(
            "Điều 35. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động "
            "không cần báo trước nếu không được trả đủ lương hoặc trả lương không đúng thời hạn."
        ),
    )


def test_verifier_accepts_valid_citation() -> None:
    result = verify_citations(
        (
            "Theo Điều 35 Bộ luật Lao động 2019, người lao động có quyền nghỉ ngay "
            "nếu không được trả lương đúng hạn [1]."
        ),
        [labor_reference()],
    )

    assert result.passed is True
    assert result.as_dict() == {
        "passed": True,
        "errors": [],
        "unsupported_citations": [],
        "invented_references": [],
        "missing_citations": [],
    }


def test_verifier_flags_citation_index_out_of_range() -> None:
    result = verify_citations("Người lao động có quyền nghỉ ngay [2].", [labor_reference()])

    assert result.passed is False
    assert result.unsupported_citations == ("[2]",)
    assert "Unsupported bracket citation: [2]" in result.errors


def test_verifier_flags_invented_article_number() -> None:
    result = verify_citations(
        "Điều 999 quy định người lao động có quyền nghỉ ngay khi chậm lương [1].",
        [labor_reference()],
    )

    assert result.passed is False
    assert "Điều 999" in result.invented_references


def test_verifier_flags_legal_claim_without_citation() -> None:
    result = verify_citations(
        "Người lao động có quyền đơn phương chấm dứt hợp đồng khi không được trả lương đúng hạn.",
        [labor_reference()],
    )

    assert result.passed is False
    assert result.missing_citations
    assert "người lao động có quyền" in result.missing_citations[0].lower()


def test_example_verifier_output_shape() -> None:
    assert EXAMPLE_VERIFIER_OUTPUT == {
        "passed": False,
        "errors": [
            "Unsupported bracket citation: [9]",
            "Invented or unsupported legal reference: Điều 999",
        ],
        "unsupported_citations": ["[9]"],
        "invented_references": ["Điều 999"],
        "missing_citations": [],
    }
