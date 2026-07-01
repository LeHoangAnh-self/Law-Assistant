from datetime import date

from rag_service.models import SourceReference
from rag_service.source_policy import (
    assess_source_quality,
    build_retrieval_diagnostics,
    source_quality_lines,
)


def source(
    title: str,
    validity_status: str = "Còn hiệu lực",
    effective_date: str | None = "2020-01-01",
    expired_date: str | None = None,
) -> SourceReference:
    return SourceReference(
        document_id=1,
        chunk_id="1:1",
        title=title,
        validity_status=validity_status,
        effective_date=effective_date,
        expired_date=expired_date,
        score=1,
        text="Nội dung điều khoản.",
    )


def test_source_quality_recognizes_law_as_high_authority() -> None:
    quality = assess_source_quality(source("Luật Thuế thu nhập cá nhân"))

    assert quality.hierarchy_label == "Bộ luật/Luật/Nghị quyết của Quốc hội"
    assert quality.authority_rank == 1
    assert quality.is_current is True


def test_source_quality_flags_expired_metadata_on_as_of_date() -> None:
    quality = assess_source_quality(
        source("Nghị định cũ", expired_date="2023-01-01"),
        as_of_date=date(2026, 7, 1),
    )

    assert quality.is_current is False
    assert any("Metadata ngày hiệu lực" in warning for warning in quality.warnings)


def test_retrieval_diagnostics_counts_authoritative_and_missing_sources() -> None:
    diagnostics = build_retrieval_diagnostics(
        [source("Bộ luật Lao động số 45/2019/QH14")],
        missing_required_sources=["Bộ luật Lao động 2019 Điều 48"],
        as_of_date=date(2026, 7, 1),
    )

    assert diagnostics.authoritative_source_count == 1
    assert diagnostics.expired_source_count == 0
    assert diagnostics.missing_required_sources == ("Bộ luật Lao động 2019 Điều 48",)
    assert "Thiếu một số nguồn kiểm soát" in diagnostics.warnings[0]


def test_source_quality_lines_are_prompt_ready() -> None:
    lines = source_quality_lines([source("Thông tư 111/2013/TT-BTC", "Hết hiệu lực một phần")])

    assert lines == [
        "[1] Thông tư/Thông tư liên tịch; phù hợp hiệu lực; "
        "cảnh báo: Văn bản hết hiệu lực một phần; cần kiểm tra đúng điều/khoản."
    ]
