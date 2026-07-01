from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from rag_service.models import SourceReference

ARTICLE_RE = re.compile(r"\bĐiều\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
CLAUSE_RE = re.compile(r"\bkhoản\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
POINT_RE = re.compile(r"\bđiểm\s+(?P<number>[a-zđ])\b", re.IGNORECASE)


@dataclass(frozen=True)
class ExpectedCitation:
    citation_id: int
    document_id: int
    document_number: str | None
    article_numbers: tuple[str, ...] = ()
    clause_numbers: tuple[str, ...] = ()
    point_numbers: tuple[str, ...] = ()
    cited_text: str | None = None


@dataclass(frozen=True)
class QnaBenchmarkItem:
    qna_id: int
    question: str
    reference_answer: str | None
    published_date: str | None
    citations: tuple[ExpectedCitation, ...]


def load_qna_benchmark(
    dataset_dir: str | Path,
    *,
    limit: int | None = None,
) -> list[QnaBenchmarkItem]:
    benchmark_path = Path(dataset_dir) / "government_qna_benchmark.parquet"
    if not benchmark_path.exists():
        raise FileNotFoundError(f"Missing benchmark file: {benchmark_path}")
    frame = pd.read_parquet(benchmark_path)
    if frame.empty:
        return []
    if limit is not None:
        qna_ids = list(dict.fromkeys(frame["qna_id"].tolist()))[:limit]
        frame = frame[frame["qna_id"].isin(qna_ids)]

    items: list[QnaBenchmarkItem] = []
    for qna_id, group in frame.groupby("qna_id", sort=True):
        first = group.iloc[0]
        citations = tuple(_citation_from_row(row) for _, row in group.iterrows())
        items.append(
            QnaBenchmarkItem(
                qna_id=int(qna_id),
                question=str(first["question"]),
                reference_answer=_optional_str(first.get("reference_answer")),
                published_date=_optional_str(first.get("published_date")),
                citations=citations,
            )
        )
    return items


def write_qwen_reranker_jsonl(
    rows: Iterable[dict],
    output_path: str | Path,
) -> int:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def citation_matches_reference(reference: SourceReference, citation: ExpectedCitation) -> bool:
    if reference.document_id != citation.document_id:
        return False
    haystack = _reference_haystack(reference)
    if citation.article_numbers and not any(
        _matches_ref(reference.article_number, "điều", number, haystack)
        for number in citation.article_numbers
    ):
        return False
    if citation.clause_numbers and not any(
        _matches_ref(reference.clause_number, "khoản", number, haystack)
        for number in citation.clause_numbers
    ):
        return False
    if citation.point_numbers and not any(
        _matches_ref(reference.point_number, "điểm", number, haystack)
        for number in citation.point_numbers
    ):
        return False
    return True


def document_matches_reference(reference: SourceReference, citation: ExpectedCitation) -> bool:
    return reference.document_id == citation.document_id


def reference_training_text(reference: SourceReference) -> str:
    return reference.retrieval_text or reference.text


def _citation_from_row(row) -> ExpectedCitation:
    return ExpectedCitation(
        citation_id=int(row["citation_id"]),
        document_id=int(row["expected_document_id"]),
        document_number=_optional_str(row.get("expected_document_number")),
        article_numbers=_extract_refs(row.get("article_refs"), ARTICLE_RE),
        clause_numbers=_extract_refs(row.get("clause_refs"), CLAUSE_RE),
        point_numbers=_extract_refs(row.get("point_refs"), POINT_RE),
        cited_text=_optional_str(row.get("cited_text")),
    )


def _matches_ref(value: str | None, label: str, expected: str, haystack: str) -> bool:
    normalized = _normalize_ref(value)
    return normalized == expected or f"{label} {expected}" in haystack


def _extract_refs(value, pattern: re.Pattern[str]) -> tuple[str, ...]:
    text = _optional_str(value)
    if not text:
        return ()
    return tuple(
        dict.fromkeys(
            _normalize_ref(match.group("number"))
            for match in pattern.finditer(text)
        )
    )


def _normalize_ref(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip(".,;:)").lower()


def _reference_haystack(reference: SourceReference) -> str:
    return " ".join(
        value or ""
        for value in [
            reference.title,
            reference.document_number,
            reference.legal_path,
            reference.article_number,
            reference.clause_number,
            reference.point_number,
            reference.text,
            reference.retrieval_text,
        ]
    ).casefold()


def _optional_str(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None
