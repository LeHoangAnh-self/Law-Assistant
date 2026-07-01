import re
import unicodedata
from dataclasses import dataclass

from rag_service.models import SourceReference

BRACKET_CITATION_RE = re.compile(r"\[(?P<index>\d{1,3})\]")
DOCUMENT_NUMBER_RE = re.compile(
    r"\b\d{1,4}/\d{4}/[A-ZĐÂÊÔƠƯ0-9.-]+(?:-[A-ZĐÂÊÔƠƯ0-9.-]+)*\b",
    re.IGNORECASE,
)
ARTICLE_REF_RE = re.compile(r"\bĐiều\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
CLAUSE_REF_RE = re.compile(r"\bkhoản\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
POINT_REF_RE = re.compile(r"\bđiểm\s+(?P<number>[a-zđ])\b", re.IGNORECASE)
LEGAL_DOCUMENT_NAME_RE = re.compile(
    r"\b(?P<name>"
    r"(?:Bộ\s+luật|Luật|Nghị\s+định|Thông\s+tư|Nghị\s+quyết|Quyết\s+định|Pháp\s+lệnh)"
    r"(?:\s+số)?\s+[^\n\[\].,;:()]{2,120})",
    re.IGNORECASE,
)
LEGAL_CLAIM_RE = re.compile(
    r"\b("
    r"theo|quy định|phải|được|không được|có quyền|nghĩa vụ|trách nhiệm|điều kiện|"
    r"hồ sơ|thời hạn|xử phạt|thuế|hợp đồng|người lao động|người sử dụng lao động|"
    r"bảo hiểm xã hội|chuyển nhượng|miễn thuế|bồi thường|lệ phí|đăng ký|cấp giấy phép"
    r")\b",
    re.IGNORECASE,
)
INSUFFICIENT_EVIDENCE_RE = re.compile(
    r"chưa đủ|không đủ căn cứ|không thể xác minh|không tìm thấy|thiếu căn cứ",
    re.IGNORECASE,
)
GENERIC_DOCUMENT_BODY_STARTS = (
    "ap dung",
    "hien hanh",
    "quy dinh",
    "lien quan",
    "nay",
    "nao",
    "truc tiep",
    "kiem soat",
    "nen tang",
    "cho",
    "ve",
)


@dataclass(frozen=True)
class CitationVerifierResult:
    passed: bool
    errors: tuple[str, ...] = ()
    unsupported_citations: tuple[str, ...] = ()
    invented_references: tuple[str, ...] = ()
    missing_citations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "unsupported_citations": list(self.unsupported_citations),
            "invented_references": list(self.invented_references),
            "missing_citations": list(self.missing_citations),
        }


@dataclass(frozen=True)
class CitationEvidence:
    citation_indices: frozenset[int]
    document_numbers: frozenset[str]
    document_aliases: frozenset[str]
    article_numbers: frozenset[str]
    clause_numbers: frozenset[str]
    point_numbers: frozenset[str]


EXAMPLE_VERIFIER_OUTPUT = {
    "passed": False,
    "errors": [
        "Unsupported bracket citation: [9]",
        "Invented or unsupported legal reference: Điều 999",
    ],
    "unsupported_citations": ["[9]"],
    "invented_references": ["Điều 999"],
    "missing_citations": [],
}


def verify_citations(answer: str, references: list[SourceReference]) -> CitationVerifierResult:
    evidence = _build_evidence(references)
    unsupported_citations = _unsupported_bracket_citations(answer, evidence)
    invented_references = _invented_references(answer, evidence)
    missing_citations = _missing_citations(answer)

    errors: list[str] = []
    errors.extend(f"Unsupported bracket citation: {citation}" for citation in unsupported_citations)
    errors.extend(
        f"Invented or unsupported legal reference: {reference}"
        for reference in invented_references
    )
    errors.extend(f"Missing citation for legal claim: {claim}" for claim in missing_citations)

    return CitationVerifierResult(
        passed=not errors,
        errors=tuple(_dedupe_preserve_order(errors)),
        unsupported_citations=tuple(unsupported_citations),
        invented_references=tuple(invented_references),
        missing_citations=tuple(missing_citations),
    )


def _build_evidence(references: list[SourceReference]) -> CitationEvidence:
    document_numbers: set[str] = set()
    document_aliases: set[str] = set()
    article_numbers: set[str] = set()
    clause_numbers: set[str] = set()
    point_numbers: set[str] = set()

    for reference in references:
        if reference.document_number:
            document_numbers.add(_normalize_document_number(reference.document_number))
        document_aliases.update(_document_aliases(reference))

        for value in (reference.article_number, reference.parent_article_number):
            normalized = _normalize_ref_number(value)
            if normalized:
                article_numbers.add(normalized)
        for value in (reference.clause_number,):
            normalized = _normalize_ref_number(value)
            if normalized:
                clause_numbers.add(normalized)
        for value in (reference.point_number,):
            normalized = _normalize_point_label(value)
            if normalized:
                point_numbers.add(normalized)

        haystack = _reference_haystack(reference)
        article_numbers.update(
            _normalize_ref_number(match.group("number"))
            for match in ARTICLE_REF_RE.finditer(haystack)
        )
        clause_numbers.update(
            _normalize_ref_number(match.group("number"))
            for match in CLAUSE_REF_RE.finditer(haystack)
        )
        point_numbers.update(
            _normalize_point_label(match.group("number"))
            for match in POINT_REF_RE.finditer(haystack)
        )

    return CitationEvidence(
        citation_indices=frozenset(range(1, len(references) + 1)),
        document_numbers=frozenset(document_numbers),
        document_aliases=frozenset(alias for alias in document_aliases if alias),
        article_numbers=frozenset(number for number in article_numbers if number),
        clause_numbers=frozenset(number for number in clause_numbers if number),
        point_numbers=frozenset(number for number in point_numbers if number),
    )


def _unsupported_bracket_citations(answer: str, evidence: CitationEvidence) -> list[str]:
    unsupported: list[str] = []
    for citation_index in _bracket_citation_indices(answer):
        if citation_index not in evidence.citation_indices:
            unsupported.append(f"[{citation_index}]")
    return _dedupe_preserve_order(unsupported)


def _invented_references(answer: str, evidence: CitationEvidence) -> list[str]:
    invented: list[str] = []

    for document_number in _extract_document_numbers(answer):
        if document_number not in evidence.document_numbers:
            invented.append(f"Văn bản {document_number}")

    for document_name in _extract_document_names(answer):
        if not _document_name_supported(document_name, evidence):
            invented.append(document_name)

    for article_number in _extract_article_numbers(answer):
        if article_number not in evidence.article_numbers:
            invented.append(f"Điều {article_number}")

    for clause_number in _extract_clause_numbers(answer):
        if evidence.clause_numbers and clause_number not in evidence.clause_numbers:
            invented.append(f"khoản {clause_number}")

    for point_number in _extract_point_numbers(answer):
        if evidence.point_numbers and point_number not in evidence.point_numbers:
            invented.append(f"điểm {point_number}")

    return _dedupe_preserve_order(invented)


def _missing_citations(answer: str) -> list[str]:
    missing: list[str] = []
    for segment in _claim_segments(answer):
        if BRACKET_CITATION_RE.search(segment):
            continue
        if not segment or INSUFFICIENT_EVIDENCE_RE.search(segment):
            continue
        if _contains_legal_claim(segment):
            missing.append(_compact_snippet(segment))
    return _dedupe_preserve_order(missing)


def _bracket_citation_indices(answer: str) -> list[int]:
    return [int(match.group("index")) for match in BRACKET_CITATION_RE.finditer(answer)]


def _extract_document_numbers(text: str) -> list[str]:
    return _dedupe_preserve_order(
        _normalize_document_number(match.group(0)) for match in DOCUMENT_NUMBER_RE.finditer(text)
    )


def _extract_article_numbers(text: str) -> list[str]:
    return _dedupe_preserve_order(
        _normalize_ref_number(match.group("number")) for match in ARTICLE_REF_RE.finditer(text)
    )


def _extract_clause_numbers(text: str) -> list[str]:
    return _dedupe_preserve_order(
        _normalize_ref_number(match.group("number")) for match in CLAUSE_REF_RE.finditer(text)
    )


def _extract_point_numbers(text: str) -> list[str]:
    return _dedupe_preserve_order(
        _normalize_point_label(match.group("number")) for match in POINT_REF_RE.finditer(text)
    )


def _extract_document_names(text: str) -> list[str]:
    names: list[str] = []
    for match in LEGAL_DOCUMENT_NAME_RE.finditer(text):
        name = _trim_document_name(match.group("name"))
        if _looks_like_generic_document_phrase(name):
            continue
        if DOCUMENT_NUMBER_RE.search(name) or _document_name_has_specific_body(name):
            names.append(name)
    return _dedupe_preserve_order(names)


def _document_name_supported(document_name: str, evidence: CitationEvidence) -> bool:
    document_numbers = _extract_document_numbers(document_name)
    if document_numbers and all(number in evidence.document_numbers for number in document_numbers):
        return True

    normalized = _normalize_name_text(_remove_document_numbers(document_name))
    for alias in evidence.document_aliases:
        if alias and (alias in normalized or normalized in alias):
            return True
    return False


def _document_aliases(reference: SourceReference) -> set[str]:
    aliases: set[str] = set()
    document_number = reference.document_number or ""
    for raw_value in (reference.title, reference.document_type):
        if not raw_value:
            continue
        normalized = _normalize_name_text(_remove_document_numbers(raw_value))
        normalized = _normalize_name_text(
            re.sub(r"\bso\b\s*$", "", normalized, flags=re.IGNORECASE)
        )
        if _is_useful_document_alias(normalized):
            aliases.add(normalized)
    if reference.title and document_number:
        title_without_number = _remove_document_numbers(
            reference.title.replace(document_number, "")
        )
        normalized = _normalize_name_text(title_without_number)
        if _is_useful_document_alias(normalized):
            aliases.add(normalized)
    return aliases


def _is_useful_document_alias(value: str) -> bool:
    words = value.split()
    return len(words) >= 2 and value not in {
        "bo luat",
        "luat",
        "nghi dinh",
        "thong tu",
        "nghi quyet",
        "quyet dinh",
        "phap lenh",
    }


def _document_name_has_specific_body(name: str) -> bool:
    normalized = _normalize_name_text(_remove_document_numbers(name))
    if re.search(r"\b(19|20)\d{2}\b", name):
        return True
    if any(normalized.startswith(prefix) for prefix in ("bo luat", "luat", "nghi dinh")):
        return len(normalized.split()) <= 8 and len(normalized.split()) >= 3
    return len(normalized.split()) <= 10 and len(normalized.split()) >= 3


def _looks_like_generic_document_phrase(name: str) -> bool:
    normalized = _normalize_name_text(_remove_document_numbers(name))
    words = normalized.split()
    if len(words) < 2:
        return True
    body = " ".join(words[1:])
    if words[:2] == ["bo", "luat"]:
        body = " ".join(words[2:])
    return any(body.startswith(prefix) for prefix in GENERIC_DOCUMENT_BODY_STARTS)


def _trim_document_name(name: str) -> str:
    name = re.split(
        r"\s+(?:theo|cho|về|để|khi|nếu|nhưng|và|hoặc|thì|tại|trong)\s+",
        name.strip(),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return name.strip(" \t\r\n.,;:()")


def _remove_document_numbers(value: str) -> str:
    return DOCUMENT_NUMBER_RE.sub("", value)


def _contains_legal_claim(text: str) -> bool:
    return bool(
        ARTICLE_REF_RE.search(text)
        or DOCUMENT_NUMBER_RE.search(text)
        or LEGAL_DOCUMENT_NAME_RE.search(text)
        or LEGAL_CLAIM_RE.search(text)
    )


def _claim_segments(answer: str) -> list[str]:
    segments: list[str] = []
    for raw_line in answer.splitlines():
        line = _strip_heading_line(raw_line.strip())
        if not line:
            continue
        segments.extend(
            segment.strip()
            for segment in re.split(r"(?<=[.!?])\s+|(?<=\])\s+", line)
            if segment.strip()
        )
    return segments


def _strip_heading_line(line: str) -> str:
    if re.match(r"^\s*(?:#{1,6}\s*)?\d+\.\s*[^.!?]{1,80}$", line):
        return ""
    if re.match(r"^\s*(?:#{1,6}\s*)?[A-ZĐÂÊÔƠƯa-zà-ỹ\s]{1,60}:?\s*$", line):
        return ""
    return line


def _reference_haystack(reference: SourceReference) -> str:
    return " ".join(
        value or ""
        for value in [
            reference.title,
            reference.document_number,
            reference.legal_path,
            reference.text,
            reference.retrieval_text,
            reference.child_text,
            reference.parent_text,
        ]
    )


def _normalize_document_number(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip(".,;:)").upper()


def _normalize_ref_number(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").strip(".,;:)").lower()


def _normalize_point_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_name_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    without_accents = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    without_accents = without_accents.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zA-Z]+", " ", without_accents).lower()).strip()


def _compact_snippet(value: str, limit: int = 180) -> str:
    compacted = " ".join(value.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 1].rstrip() + "…"


def _dedupe_preserve_order(values) -> list:
    seen = set()
    deduped = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
