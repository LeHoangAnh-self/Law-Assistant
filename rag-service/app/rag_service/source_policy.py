from dataclasses import dataclass
from datetime import date

from rag_service.models import SourceReference


@dataclass(frozen=True)
class SourceQuality:
    hierarchy_label: str
    authority_rank: int
    is_current: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalDiagnostics:
    authoritative_source_count: int
    expired_source_count: int
    missing_required_sources: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


LAW_SOURCE_HIERARCHY = (
    "Hiến pháp",
    "Bộ luật/Luật/Nghị quyết của Quốc hội",
    "Pháp lệnh/Nghị quyết của UBTVQH",
    "Nghị định/Quyết định của Chính phủ, Thủ tướng",
    "Thông tư/Thông tư liên tịch",
    "Quyết định/Công văn/Hướng dẫn chính thức",
    "Nguồn khác/bình luận",
)


def assess_source_quality(
    reference: SourceReference,
    as_of_date: date | None = None,
) -> SourceQuality:
    text = _reference_haystack(reference)
    authority_rank = _law_authority_rank(text)
    warnings: list[str] = []

    status = (reference.validity_status or "").lower()
    is_current = True
    if "hết hiệu lực toàn bộ" in status:
        is_current = False
        warnings.append("Văn bản đã hết hiệu lực toàn bộ.")
    elif "chưa có hiệu lực" in status:
        is_current = False
        warnings.append("Văn bản chưa có hiệu lực tại metadata.")
    elif "hết hiệu lực một phần" in status:
        warnings.append("Văn bản hết hiệu lực một phần; cần kiểm tra đúng điều/khoản.")

    if as_of_date and not _valid_on_date(reference, as_of_date):
        is_current = False
        warnings.append(
            f"Metadata ngày hiệu lực không phù hợp ngày đánh giá {as_of_date.isoformat()}."
        )

    return SourceQuality(
        hierarchy_label=LAW_SOURCE_HIERARCHY[min(authority_rank, len(LAW_SOURCE_HIERARCHY) - 1)],
        authority_rank=authority_rank,
        is_current=is_current,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def authority_score_bonus(reference: SourceReference) -> float:
    quality = assess_source_quality(reference)
    # Lower rank means higher authority. Keep this small enough that relevance still matters.
    bonus_by_rank = {
        0: 3.0,
        1: 2.5,
        2: 1.75,
        3: 1.25,
        4: 0.75,
        5: 0.25,
        6: -0.5,
    }
    bonus = bonus_by_rank.get(quality.authority_rank, -0.5)
    if not quality.is_current:
        bonus -= 4.0
    elif reference.validity_status and "hết hiệu lực một phần" in reference.validity_status.lower():
        bonus -= 0.25
    return bonus


def build_retrieval_diagnostics(
    references: list[SourceReference],
    missing_required_sources: list[str] | tuple[str, ...],
    as_of_date: date | None = None,
) -> RetrievalDiagnostics:
    qualities = [
        assess_source_quality(reference, as_of_date=as_of_date)
        for reference in references
    ]
    authoritative_count = sum(
        1 for quality in qualities if quality.authority_rank <= 4 and quality.is_current
    )
    expired_count = sum(1 for quality in qualities if not quality.is_current)
    warnings: list[str] = []
    if not references:
        warnings.append("Không có nguồn truy xuất để tạo câu trả lời có căn cứ.")
    if expired_count and authoritative_count == 0:
        warnings.append("Các nguồn mạnh nhất có vấn đề hiệu lực; không nên kết luận dứt khoát.")
    if missing_required_sources:
        warnings.append("Thiếu một số nguồn kiểm soát bắt buộc cho issue đã phân loại.")
    return RetrievalDiagnostics(
        authoritative_source_count=authoritative_count,
        expired_source_count=expired_count,
        missing_required_sources=tuple(missing_required_sources),
        warnings=tuple(warnings),
    )


def source_quality_lines(
    references: list[SourceReference],
    as_of_date: date | None = None,
) -> list[str]:
    lines = []
    for index, reference in enumerate(references, start=1):
        quality = assess_source_quality(reference, as_of_date=as_of_date)
        warning_text = f"; cảnh báo: {'; '.join(quality.warnings)}" if quality.warnings else ""
        lines.append(
            f"[{index}] {quality.hierarchy_label}; "
            f"{'phù hợp hiệu lực' if quality.is_current else 'không phù hợp/chưa chắc hiệu lực'}"
            f"{warning_text}"
        )
    return lines


def _law_authority_rank(text: str) -> int:
    if "hiến pháp" in text:
        return 0
    if any(
        term in text
        for term in ["bộ luật", " luật ", "luật số", "nghị quyết của quốc hội"]
    ) or text.startswith("luật "):
        return 1
    if any(term in text for term in ["pháp lệnh", "ủy ban thường vụ quốc hội", "ubtvqh"]):
        return 2
    if any(term in text for term in ["nghị định", "quyết định của thủ tướng", "chính phủ"]):
        return 3
    if any(term in text for term in ["thông tư", "thông tư liên tịch"]):
        return 4
    if any(term in text for term in ["công văn", "hướng dẫn", "quyết định"]):
        return 5
    return 6


def _valid_on_date(reference: SourceReference, as_of_date: date) -> bool:
    effective_date = _parse_iso_date(reference.effective_date)
    expired_date = _parse_iso_date(reference.expired_date)
    issued_date = _parse_iso_date(reference.issued_date)
    if effective_date and effective_date > as_of_date:
        return False
    if not effective_date and issued_date and issued_date > as_of_date:
        return False
    if expired_date and expired_date <= as_of_date:
        return False
    return True


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _reference_haystack(reference: SourceReference) -> str:
    return " ".join(
        value or ""
        for value in [
            reference.title,
            reference.document_number,
            reference.document_type,
            reference.issuing_authority,
            reference.source,
            reference.source_url,
            reference.legal_path,
            reference.text[:1200],
        ]
    ).lower()
