import re
from dataclasses import dataclass

LEGAL_BOUNDARY_RE = re.compile(
    r"(?m)^(?P<label>Phần|Chương|Mục|Tiểu mục|Điều)\s+"
    r"(?P<number>[IVXLCDM\d]+[A-ZĐ]?(?:[./-]\d+)*)\b[^\n]*"
)
CLAUSE_BOUNDARY_RE = re.compile(r"(?m)^(?P<number>\d+)\.\s+")
POINT_BOUNDARY_RE = re.compile(r"(?m)^(?P<number>[a-zđ])\)\s+")
INLINE_WS_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class LegalChunk:
    text: str
    retrieval_text: str
    char_start: int
    char_end: int
    legal_path: str | None = None
    article_number: str | None = None
    clause_number: str | None = None
    point_number: str | None = None
    chunking_strategy: str = "legal_structure_v1"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_legal_text(text: str) -> str:
    lines = [INLINE_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    return MULTI_NEWLINE_RE.sub("\n\n", "\n".join(line for line in lines if line)).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    return [chunk.text for chunk in chunk_legal_text(text, chunk_size, overlap)]


def chunk_legal_text(
    text: str,
    chunk_size: int,
    overlap: int,
    document_context: str | None = None,
) -> list[LegalChunk]:
    text = normalize_legal_text(text)
    if not text:
        return []
    _validate_chunk_limits(chunk_size, overlap)

    sections = _legal_sections(text)
    chunks: list[LegalChunk] = []
    for section_index, section in enumerate(sections):
        if section_index + 1 < len(sections):
            next_section_start = sections[section_index + 1].start
        else:
            next_section_start = len(text)
        section_chunks = _split_section(
            text=text,
            section=section,
            next_section_start=next_section_start,
            chunk_size=chunk_size,
            overlap=overlap,
            document_context=document_context,
        )
        chunks.extend(section_chunks)

    if chunks:
        return chunks
    return _fixed_window_chunks(text, chunk_size, overlap, document_context=document_context)


def _validate_chunk_limits(chunk_size: int, overlap: int) -> None:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")


@dataclass(frozen=True)
class _Section:
    start: int
    end: int
    label: str
    number: str
    heading: str
    path: str


def _legal_sections(text: str) -> list[_Section]:
    matches = list(LEGAL_BOUNDARY_RE.finditer(text))
    if not matches:
        return []

    sections: list[_Section] = []
    current_path: dict[str, str] = {}
    path_order = ["Phần", "Chương", "Mục", "Tiểu mục", "Điều"]
    path_rank = {label: index for index, label in enumerate(path_order)}

    for index, match in enumerate(matches):
        label = match.group("label")
        number = match.group("number")
        heading = match.group(0).strip()
        rank = path_rank[label]
        for existing_label in list(current_path):
            if path_rank[existing_label] >= rank:
                current_path.pop(existing_label, None)
        current_path[label] = heading
        path = " > ".join(current_path[item] for item in path_order if item in current_path)
        sections.append(
            _Section(
                start=match.start(),
                end=matches[index + 1].start() if index + 1 < len(matches) else len(text),
                label=label,
                number=number,
                heading=heading,
                path=path,
            )
        )
    return sections


def _split_section(
    text: str,
    section: _Section,
    next_section_start: int,
    chunk_size: int,
    overlap: int,
    document_context: str | None,
) -> list[LegalChunk]:
    section_text = text[section.start:section.end].strip()
    if not section_text:
        return []
    if len(section_text) <= chunk_size:
        return [
            _build_chunk(
                text=section_text,
                char_start=section.start,
                char_end=section.end,
                legal_path=section.path,
                article_number=section.number if section.label == "Điều" else None,
                document_context=document_context,
            )
        ]

    if section.label == "Điều":
        subordinate_chunks = _subdivide_article(
            text,
            section,
            chunk_size,
            overlap,
            document_context,
        )
        if subordinate_chunks:
            return subordinate_chunks

    # Non-article sections usually contain many articles. If a legal heading is oversized,
    # use fixed windows inside that heading while preserving the heading path.
    fixed_chunks = _fixed_window_chunks(
        text[section.start:next_section_start],
        chunk_size,
        overlap,
        offset=section.start,
        legal_path=section.path,
        article_number=section.number if section.label == "Điều" else None,
        document_context=document_context,
    )
    return fixed_chunks


def _subdivide_article(
    text: str,
    section: _Section,
    chunk_size: int,
    overlap: int,
    document_context: str | None,
) -> list[LegalChunk]:
    article_text = text[section.start:section.end]
    clause_matches = list(CLAUSE_BOUNDARY_RE.finditer(article_text))
    point_matches = list(POINT_BOUNDARY_RE.finditer(article_text))
    boundaries = clause_matches or point_matches
    if not boundaries:
        return []

    heading_end = article_text.find("\n")
    heading_prefix = article_text[:heading_end].strip() if heading_end > -1 else section.heading
    chunks: list[LegalChunk] = []
    for index, match in enumerate(boundaries):
        part_start = section.start + match.start()
        if index + 1 < len(boundaries):
            part_end = section.start + boundaries[index + 1].start()
        else:
            part_end = section.start + len(article_text)
        part = text[part_start:part_end].strip()
        if not part:
            continue
        if heading_prefix and not part.startswith(heading_prefix):
            prefixed_part = f"{heading_prefix}\n{part}"
        else:
            prefixed_part = part
        if len(prefixed_part) <= chunk_size:
            chunks.append(
                _build_chunk(
                    text=prefixed_part,
                    char_start=section.start,
                    char_end=part_end,
                    legal_path=section.path,
                    article_number=section.number,
                    clause_number=match.group("number") if clause_matches else None,
                    point_number=match.group("number") if not clause_matches else None,
                    document_context=document_context,
                )
            )
            continue
        chunks.extend(
            _fixed_window_chunks(
                prefixed_part,
                chunk_size,
                overlap,
                offset=section.start,
                legal_path=section.path,
                article_number=section.number,
                clause_number=match.group("number") if clause_matches else None,
                point_number=match.group("number") if not clause_matches else None,
                document_context=document_context,
            )
        )
    return chunks


def _fixed_window_chunks(
    text: str,
    chunk_size: int,
    overlap: int,
    *,
    offset: int = 0,
    legal_path: str | None = None,
    article_number: str | None = None,
    clause_number: str | None = None,
    point_number: str | None = None,
    document_context: str | None = None,
) -> list[LegalChunk]:
    _validate_chunk_limits(chunk_size, overlap)
    text = text.strip()
    if not text:
        return []

    chunks: list[LegalChunk] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        window = text[start:end]
        if end < len(text):
            candidates = [
                window.rfind("\nĐiều "),
                window.rfind("\nChương "),
                window.rfind("\nMục "),
                window.rfind("\n"),
                window.rfind(". "),
                window.rfind("; "),
            ]
            split_at = max(candidates)
            if split_at > chunk_size // 2:
                end = start + split_at + 1
                window = text[start:end]
        chunk = window.strip()
        if chunk:
            chunks.append(
                _build_chunk(
                    text=chunk,
                    char_start=offset + start,
                    char_end=offset + end,
                    legal_path=legal_path,
                    article_number=article_number,
                    clause_number=clause_number,
                    point_number=point_number,
                    document_context=document_context,
                )
            )
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks


def _build_chunk(
    *,
    text: str,
    char_start: int,
    char_end: int,
    legal_path: str | None,
    article_number: str | None = None,
    clause_number: str | None = None,
    point_number: str | None = None,
    document_context: str | None = None,
) -> LegalChunk:
    legal_location = f"Vị trí pháp lý: {legal_path}" if legal_path else None
    context_parts = [part for part in [document_context, legal_location] if part]
    if context_parts:
        retrieval_text = "\n".join(context_parts + [f"Nội dung đoạn:\n{text}"])
    else:
        retrieval_text = text
    return LegalChunk(
        text=text,
        retrieval_text=retrieval_text,
        char_start=char_start,
        char_end=char_end,
        legal_path=legal_path,
        article_number=article_number,
        clause_number=clause_number,
        point_number=point_number,
    )
