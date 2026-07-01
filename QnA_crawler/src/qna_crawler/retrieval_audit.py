from __future__ import annotations

from dataclasses import dataclass
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import Engine, text


ARTICLE_NUMBER_RE = re.compile(r"\bĐiều\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
CLAUSE_NUMBER_RE = re.compile(r"\bkhoản\s+(?P<number>\d+[a-zA-Z]?)\b", re.IGNORECASE)
POINT_LABEL_RE = re.compile(r"\bđiểm\s+(?P<number>[a-zđ])\b", re.IGNORECASE)


@dataclass(frozen=True)
class CitationAuditRow:
    citation_id: int
    qna_id: int
    expected_document_id: int | None
    expected_document_number: str | None
    article_numbers: tuple[str, ...]
    clause_numbers: tuple[str, ...]
    point_labels: tuple[str, ...]
    status: str
    indexed_chunk_count: int
    matched_article_numbers: tuple[str, ...] = ()
    matched_clause_numbers: tuple[str, ...] = ()
    matched_point_labels: tuple[str, ...] = ()
    raw_text: str | None = None
    question: str | None = None


@dataclass(frozen=True)
class RetrievalAuditSummary:
    checked_citations: int
    unmatched_document_db_citations: int
    ready_citations: int
    document_not_indexed: int
    article_not_indexed: int
    clause_not_indexed: int
    point_not_indexed: int
    no_structural_refs: int
    output_jsonl: Path | None = None


class QdrantPayloadClient:
    def __init__(self, base_url: str, collection: str, timeout_seconds: float = 30.0, page_size: int = 256) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection = collection
        self.timeout_seconds = timeout_seconds
        self.page_size = page_size

    def scroll_document_payloads(self, document_id: int, limit: int = 5000) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        offset: Any = None
        while len(points) < limit:
            body: dict[str, Any] = {
                "filter": {
                    "must": [
                        {
                            "key": "document_id",
                            "match": {"value": document_id},
                        }
                    ]
                },
                "limit": min(self.page_size, limit - len(points)),
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            try:
                response = requests.post(
                    f"{self.base_url}/collections/{self.collection}/points/scroll",
                    json=body,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Qdrant is not reachable at {self.base_url} or collection "
                    f"{self.collection!r} cannot be read"
                ) from exc
            result = response.json().get("result") or {}
            batch = result.get("points") or []
            points.extend(point.get("payload") or {} for point in batch)
            offset = result.get("next_page_offset")
            if not batch or offset is None:
                break
        return points


def audit_qna_retrieval_readiness(
    engine: Engine,
    qdrant_client: QdrantPayloadClient,
    *,
    limit: int | None = None,
    output_jsonl: str | Path | None = None,
    progress_every: int = 500,
) -> RetrievalAuditSummary:
    rows = _load_citation_rows(engine, limit=limit)
    output_path = Path(output_jsonl) if output_jsonl else None
    output_handle = output_path.open("w", encoding="utf-8") if output_path else None

    checked = 0
    unmatched = 0
    ready = 0
    document_not_indexed = 0
    article_not_indexed = 0
    clause_not_indexed = 0
    point_not_indexed = 0
    no_structural_refs = 0
    payload_cache: dict[int, list[dict[str, Any]]] = {}

    try:
        for row in rows:
            audit_row: CitationAuditRow
            if row["matched_document_id"] is None:
                unmatched += 1
                audit_row = CitationAuditRow(
                    citation_id=int(row["citation_id"]),
                    qna_id=int(row["qna_id"]),
                    expected_document_id=None,
                    expected_document_number=row["matched_document_number"],
                    article_numbers=_citation_ref_numbers(row, "article_refs", ARTICLE_NUMBER_RE),
                    clause_numbers=_citation_ref_numbers(row, "clause_refs", CLAUSE_NUMBER_RE),
                    point_labels=_citation_ref_numbers(row, "point_refs", POINT_LABEL_RE),
                    status=row["match_status"],
                    indexed_chunk_count=0,
                    raw_text=row["raw_text"],
                    question=row["question"],
                )
            else:
                checked += 1
                document_id = int(row["matched_document_id"])
                if document_id not in payload_cache:
                    payload_cache[document_id] = qdrant_client.scroll_document_payloads(document_id)
                audit_row = _audit_matched_citation(row, payload_cache[document_id])
                if audit_row.status == "RETRIEVAL_READY":
                    ready += 1
                elif audit_row.status == "DOCUMENT_NOT_INDEXED":
                    document_not_indexed += 1
                elif audit_row.status == "ARTICLE_NOT_INDEXED":
                    article_not_indexed += 1
                elif audit_row.status == "CLAUSE_NOT_INDEXED":
                    clause_not_indexed += 1
                elif audit_row.status == "POINT_NOT_INDEXED":
                    point_not_indexed += 1
                elif audit_row.status == "NO_STRUCTURAL_REFS":
                    no_structural_refs += 1

            if output_handle:
                output_handle.write(json.dumps(audit_row.__dict__, ensure_ascii=False, default=list) + "\n")
            processed = checked + unmatched
            if progress_every and processed % progress_every == 0:
                print(f"audited={processed:,} ready={ready:,} document_not_indexed={document_not_indexed:,}", file=sys.stderr, flush=True)
    finally:
        if output_handle:
            output_handle.close()

    return RetrievalAuditSummary(
        checked_citations=checked,
        unmatched_document_db_citations=unmatched,
        ready_citations=ready,
        document_not_indexed=document_not_indexed,
        article_not_indexed=article_not_indexed,
        clause_not_indexed=clause_not_indexed,
        point_not_indexed=point_not_indexed,
        no_structural_refs=no_structural_refs,
        output_jsonl=output_path,
    )


def _audit_matched_citation(row: dict[str, Any], payloads: list[dict[str, Any]]) -> CitationAuditRow:
    article_numbers = _citation_ref_numbers(row, "article_refs", ARTICLE_NUMBER_RE)
    clause_numbers = _citation_ref_numbers(row, "clause_refs", CLAUSE_NUMBER_RE)
    point_labels = _citation_ref_numbers(row, "point_refs", POINT_LABEL_RE)
    if not payloads:
        status = "DOCUMENT_NOT_INDEXED"
        matched_article_numbers: tuple[str, ...] = ()
        matched_clause_numbers: tuple[str, ...] = ()
        matched_point_labels: tuple[str, ...] = ()
    else:
        matched_article_numbers = tuple(number for number in article_numbers if _payloads_match_ref(payloads, "article_number", "điều", number))
        matched_clause_numbers = tuple(number for number in clause_numbers if _payloads_match_ref(payloads, "clause_number", "khoản", number))
        matched_point_labels = tuple(label for label in point_labels if _payloads_match_ref(payloads, "point_number", "điểm", label))

        if article_numbers and len(matched_article_numbers) < len(article_numbers):
            status = "ARTICLE_NOT_INDEXED"
        elif clause_numbers and len(matched_clause_numbers) < len(clause_numbers):
            status = "CLAUSE_NOT_INDEXED"
        elif point_labels and len(matched_point_labels) < len(point_labels):
            status = "POINT_NOT_INDEXED"
        elif not article_numbers and not clause_numbers and not point_labels:
            status = "NO_STRUCTURAL_REFS"
        else:
            status = "RETRIEVAL_READY"

    return CitationAuditRow(
        citation_id=int(row["citation_id"]),
        qna_id=int(row["qna_id"]),
        expected_document_id=int(row["matched_document_id"]),
        expected_document_number=row["matched_document_number"],
        article_numbers=article_numbers,
        clause_numbers=clause_numbers,
        point_labels=point_labels,
        status=status,
        indexed_chunk_count=len(payloads),
        matched_article_numbers=matched_article_numbers,
        matched_clause_numbers=matched_clause_numbers,
        matched_point_labels=matched_point_labels,
        raw_text=row["raw_text"],
        question=row["question"],
    )


def _payloads_match_ref(payloads: list[dict[str, Any]], field: str, label: str, expected: str) -> bool:
    for payload in payloads:
        if _normalize_ref(payload.get(field)) == expected:
            return True
        haystack = _normalize_text("\n".join(str(payload.get(key) or "") for key in ("legal_path", "text", "retrieval_text")))
        if f"{label} {expected}" in haystack:
            return True
    return False


def _load_citation_rows(engine: Engine, *, limit: int | None) -> list[dict[str, Any]]:
    query = """
        select
            c.id as citation_id,
            c.qna_item_id as qna_id,
            c.raw_text,
            c.article_refs,
            c.clause_refs,
            c.point_refs,
            c.matched_document_id,
            c.matched_document_number,
            c.match_status,
            coalesce(q.question_text, q.summary_text, q.title) as question
        from government_qna_citations c
        join government_qna_items q on q.id = c.qna_item_id
        order by c.id
    """
    params: dict[str, Any] = {}
    if limit is not None:
        query += "\nlimit :limit"
        params["limit"] = limit
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(text(query), params).mappings()]


def _extract_numbers(value: str | None, pattern: re.Pattern[str]) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(dict.fromkeys(_normalize_ref(match.group("number")) for match in pattern.finditer(value)))


def _citation_ref_numbers(row: dict[str, Any], field: str, pattern: re.Pattern[str]) -> tuple[str, ...]:
    values = []
    values.extend(_extract_numbers(row.get(field), pattern))
    values.extend(_extract_numbers(row.get("raw_text"), pattern))
    return tuple(dict.fromkeys(values))


def _normalize_ref(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip(".,;:)").lower()


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
