#!/usr/bin/env python3
# ruff: noqa: E501,I001
"""Prepare Vietnamese legal-document Parquet data for law-assistant RAG.

Inputs:
  data/metadata.parquet
  data/content.parquet
  data/relationships.parquet

The legacy folder is intentionally ignored.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


RAG_SERVICE_APP = Path(__file__).resolve().parents[3] / "rag-service" / "app"
sys.path.insert(0, str(RAG_SERVICE_APP))

from rag_service.chunking import chunk_legal_text  # noqa: E402


INPUT_FILES = {
    "metadata": "metadata.parquet",
    "content": "content.parquet",
    "relationships": "relationships.parquet",
}

CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
MAX_RELATED_DOCS_PER_SIDE = 16
CHUNK_WRITE_BATCH_SIZE = 50_000

SCRIPT_RE = re.compile(r"<(script|style)[\s\S]*?</\1>", re.IGNORECASE)
BLOCK_TAG_RE = re.compile(
    r"<\s*/?(?:br|p|div|tr|td|th|li|h[1-6]|table|tbody|thead|section|article)\b[^>]*>",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
INLINE_WS_RE = re.compile(r"[ \t\r\f\v]+")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")

RELATIONSHIP_CODES = {
    "Văn bản căn cứ": "basis_for_document",
    "Văn bản dẫn chiếu": "cited_document",
    "Văn bản hết hiệu lực": "fully_expired_by_document",
    "Văn bản quy định hết hiệu lực": "expires_other_document",
    "Văn bản được HD, QĐ chi tiết": "detailed_or_guided_by_other_document",
    "Văn bản HD, QĐ chi tiết": "details_or_guides_other_document",
    "Văn bản bổ sung": "supplements_other_document",
    "Văn bản bị hết hiệu lực 1 phần": "partly_expired_by_document",
    "Văn bản được bổ sung": "supplemented_by_other_document",
    "Văn bản được sửa đổi": "amended_by_other_document",
    "Văn bản sửa đổi": "amends_other_document",
    "Văn bản quy định hết hiệu lực 1 phần": "partly_expires_other_document",
    "Văn bản liên quan khác": "other_related_document",
    "Văn bản bị đình chỉ 1 phần": "partly_suspended_by_document",
    "Văn bản đình chỉ 1 phần": "partly_suspends_other_document",
    "Văn bản đình chỉ": "suspends_other_document",
    "Văn bản bị đình chỉ": "suspended_by_document",
}

VALIDITY_CODES = {
    "Còn hiệu lực": "active",
    "Hết hiệu lực toàn bộ": "expired_full",
    "Hết hiệu lực một phần": "expired_partial",
    "Ngưng hiệu lực": "suspended",
    "Ngưng hiệu lực một phần": "suspended_partial",
    "Chưa có hiệu lực": "not_yet_effective",
    "Không còn phù hợp": "obsolete",
    "Chưa xác định": "unknown",
    "": "unknown",
}

CONTEXT_FIELDS = [
    ("Số ký hiệu", "so_ky_hieu"),
    ("Mã nguồn ngoài", "external_docid"),
    ("Loại văn bản", "loai_van_ban"),
    ("Tình trạng hiệu lực", "tinh_trang_hieu_luc"),
    ("Ngày ban hành", "ngay_ban_hanh_iso"),
    ("Ngày hiệu lực", "ngay_co_hieu_luc_iso"),
    ("Ngày hết hiệu lực", "ngay_het_hieu_luc_iso"),
    ("Cơ quan ban hành", "co_quan_ban_hanh"),
    ("Ngành", "nganh"),
    ("Lĩnh vực", "linh_vuc"),
    ("Phạm vi", "pham_vi"),
    ("Nguồn", "nguon_thu_thap"),
    ("URL nguồn", "source_url"),
]


def clean_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).replace("\xa0", " ")
    text = INLINE_WS_RE.sub(" ", text).strip()
    if not text or text in {"...", "nan", "NaN", "None"}:
        return None
    return text


def parse_vietnamese_date(value: Any) -> str | None:
    text = clean_scalar(value)
    if not text or not DATE_RE.match(text):
        return None
    try:
        return datetime.strptime(text, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def extract_text(content_html: Any) -> str:
    text = clean_scalar(content_html) or ""
    text = SCRIPT_RE.sub(" ", text)
    text = BLOCK_TAG_RE.sub("\n", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [INLINE_WS_RE.sub(" ", line).strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return MULTI_NEWLINE_RE.sub("\n\n", text).strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[tuple[int, int, str]]:
    return [
        (chunk.char_start, chunk.char_end, chunk.text)
        for chunk in chunk_legal_text(text, chunk_size=chunk_size, overlap=overlap)
    ]


def context_header(row: pd.Series) -> str:
    lines = [f"Tiêu đề: {row['title']}"]
    for label, column in CONTEXT_FIELDS:
        value = row.get(column)
        if value:
            lines.append(f"{label}: {value}")
    summary = row.get("relationship_summary_text")
    if summary:
        lines.append(f"Quan hệ văn bản: {summary}")
    return "\n".join(lines)


def related_item(other_id: int, relation: str, metadata_by_id: dict[int, dict[str, Any]]) -> dict[str, Any]:
    other = metadata_by_id.get(other_id, {})
    return {
        "doc_id": int(other_id),
        "relationship": relation,
        "relationship_code": RELATIONSHIP_CODES.get(relation, "unknown"),
        "title": other.get("title"),
        "so_ky_hieu": other.get("so_ky_hieu"),
        "loai_van_ban": other.get("loai_van_ban"),
        "tinh_trang_hieu_luc": other.get("tinh_trang_hieu_luc"),
    }


def relationship_summary(items: list[dict[str, Any]]) -> str | None:
    if not items:
        return None
    counts = Counter(item["relationship"] for item in items)
    parts = [f"{label}: {count}" for label, count in counts.most_common()]
    return "; ".join(parts)


def write_readme(output_dir: Path, report: dict[str, Any]) -> None:
    readme = f"""# Law Assistant Prepared Dataset

Generated: {report["generated_at"]}

Source inputs:
- `data/metadata.parquet`
- `data/content.parquet`
- `data/relationships.parquet`

Excluded:
- `data/legacy/**`

## Files

- `current/metadata.parquet`: importer-compatible metadata with cleaned scalar values and original column names.
- `current/content.parquet`: importer-compatible content with original HTML and valid document ids.
- `current/relationships.parquet`: importer-compatible relationships after duplicate/self-link cleanup.
- `rag/law_documents.parquet`: one row per document with extracted `content_text`, normalized dates/status, relationship context, and `document_context`.
- `rag/law_chunks.parquet`: retrieval chunks with `retrieval_text` equal to document context plus chunk text.
- `rag/law_relationships.parquet`: deduplicated relationship graph with normalized relationship codes.
- `audit/data_quality_report.json`: source and output quality metrics.
- `audit/bad_documents.csv`: documents with empty or very short extracted text.

## RAG Notes

Use `rag/law_chunks.parquet.retrieval_text` for embeddings. Keep `document_id`, `chunk_id`,
`chunk_index`, `title`, `so_ky_hieu`, `loai_van_ban`, `tinh_trang_hieu_luc`, and date fields as payload metadata.
The raw legal text remains in `chunk_text`; `retrieval_text` adds the legal context needed for grounded answers.

Default chunking: {CHUNK_SIZE} characters with {CHUNK_OVERLAP} characters overlap.
"""
    output_dir.joinpath("README.md").write_text(readme, encoding="utf-8")


def prepare(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    input_paths = {name: input_dir / file_name for name, file_name in INPUT_FILES.items()}
    for name, path in input_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Missing {name} input: {path}")

    current_dir = output_dir / "current"
    rag_dir = output_dir / "rag"
    audit_dir = output_dir / "audit"
    current_dir.mkdir(parents=True, exist_ok=True)
    rag_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)

    print("Reading source Parquet files...", flush=True)
    metadata = pd.read_parquet(input_paths["metadata"])
    content = pd.read_parquet(input_paths["content"])
    relationships_raw = pd.read_parquet(input_paths["relationships"])

    original_relationship_rows = len(relationships_raw)
    duplicate_relationship_rows = int(relationships_raw.duplicated().sum())
    self_relationship_rows = int((relationships_raw["doc_id"] == relationships_raw["other_doc_id"]).sum())

    print("Cleaning metadata and content ids...", flush=True)
    metadata_clean = metadata.copy()
    for column in metadata_clean.columns:
        if column == "id":
            metadata_clean[column] = pd.to_numeric(metadata_clean[column], errors="raise").astype("int64")
        elif column == "thong_tin_ap_dung":
            metadata_clean[column] = pd.to_numeric(metadata_clean[column], errors="coerce")
        else:
            metadata_clean[column] = metadata_clean[column].map(clean_scalar)

    metadata_clean["ngay_ban_hanh_iso"] = metadata_clean["ngay_ban_hanh"].map(parse_vietnamese_date)
    metadata_clean["ngay_co_hieu_luc_iso"] = metadata_clean["ngay_co_hieu_luc"].map(parse_vietnamese_date)
    metadata_clean["ngay_het_hieu_luc_iso"] = metadata_clean["ngay_het_hieu_luc"].map(parse_vietnamese_date)
    metadata_clean["validity_code"] = metadata_clean["tinh_trang_hieu_luc"].fillna("").map(
        lambda value: VALIDITY_CODES.get(value, "other")
    )
    for optional_column in ["external_source", "external_docid", "source_url"]:
        if optional_column not in metadata_clean.columns:
            metadata_clean[optional_column] = None

    content_clean = content.copy()
    content_clean["id"] = pd.to_numeric(content_clean["id"], errors="raise").astype("int64")
    content_clean["content_html"] = content_clean["content_html"].map(lambda value: clean_scalar(value) or "")

    print("Extracting text from HTML content...", flush=True)
    content_text_by_id: dict[int, str] = {}
    content_hash_by_id: dict[int, str] = {}
    text_lengths: dict[int, int] = {}
    for row in pq.ParquetFile(input_paths["content"]).iter_batches(batch_size=5000, columns=["id", "content_html"]):
        ids = row.column("id").to_pylist()
        html_values = row.column("content_html").to_pylist()
        for raw_id, raw_html in zip(ids, html_values, strict=True):
            doc_id = int(raw_id)
            text = extract_text(raw_html)
            content_text_by_id[doc_id] = text
            content_hash_by_id[doc_id] = sha256_text(text)
            text_lengths[doc_id] = len(text)

    print("Deduplicating relationship graph...", flush=True)
    relationships = relationships_raw.copy()
    relationships["doc_id"] = pd.to_numeric(relationships["doc_id"], errors="raise").astype("int64")
    relationships["other_doc_id"] = pd.to_numeric(relationships["other_doc_id"], errors="raise").astype("int64")
    relationships["relationship"] = relationships["relationship"].map(clean_scalar)
    relationships = relationships.drop_duplicates()
    relationships = relationships[relationships["doc_id"] != relationships["other_doc_id"]].copy()
    relationships["relationship_code"] = relationships["relationship"].map(
        lambda value: RELATIONSHIP_CODES.get(value or "", "unknown")
    )

    metadata_ids = set(int(value) for value in metadata_clean["id"].tolist())
    content_ids = set(int(value) for value in content_clean["id"].tolist())
    relationship_doc_missing = int((~relationships["doc_id"].isin(metadata_ids)).sum())
    relationship_other_missing = int((~relationships["other_doc_id"].isin(metadata_ids)).sum())

    metadata_by_id = (
        metadata_clean[
            [
                "id",
                "title",
                "so_ky_hieu",
                "loai_van_ban",
                "tinh_trang_hieu_luc",
                "ngay_ban_hanh_iso",
                "co_quan_ban_hanh",
            ]
        ]
        .set_index("id")
        .to_dict("index")
    )

    outgoing: dict[int, list[dict[str, Any]]] = defaultdict(list)
    incoming: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for rel in relationships.itertuples(index=False):
        outgoing[int(rel.doc_id)].append(related_item(int(rel.other_doc_id), rel.relationship, metadata_by_id))
        incoming[int(rel.other_doc_id)].append(related_item(int(rel.doc_id), rel.relationship, metadata_by_id))

    print("Building document-level context...", flush=True)
    documents = metadata_clean.copy()
    documents["document_id"] = documents["id"].astype("int64")
    documents["content_text"] = documents["document_id"].map(content_text_by_id).fillna("")
    documents["content_text_length"] = documents["document_id"].map(text_lengths).fillna(0).astype("int64")
    documents["content_sha256"] = documents["document_id"].map(content_hash_by_id)

    documents["outgoing_relationships"] = documents["document_id"].map(
        lambda doc_id: json.dumps(outgoing.get(int(doc_id), [])[:MAX_RELATED_DOCS_PER_SIDE], ensure_ascii=False)
    )
    documents["incoming_relationships"] = documents["document_id"].map(
        lambda doc_id: json.dumps(incoming.get(int(doc_id), [])[:MAX_RELATED_DOCS_PER_SIDE], ensure_ascii=False)
    )
    documents["relationship_count"] = documents["document_id"].map(
        lambda doc_id: len(outgoing.get(int(doc_id), [])) + len(incoming.get(int(doc_id), []))
    )
    documents["relationship_summary_text"] = documents["document_id"].map(
        lambda doc_id: relationship_summary(outgoing.get(int(doc_id), []) + incoming.get(int(doc_id), []))
    )
    documents["document_context"] = documents.apply(context_header, axis=1)

    bad_documents = documents[
        (documents["content_text_length"] < 80) | documents["title"].isna() | (documents["title"].str.len() < 5)
    ][
        [
            "document_id",
            "title",
            "so_ky_hieu",
            "loai_van_ban",
            "tinh_trang_hieu_luc",
            "content_text_length",
            "content_sha256",
        ]
    ]
    bad_documents.to_csv(audit_dir / "bad_documents.csv", index=False)

    print("Writing importer-compatible and document-level outputs...", flush=True)
    importer_metadata_columns = [
        *metadata.columns.tolist(),
        "external_source",
        "external_docid",
        "source_url",
    ]
    importer_metadata = metadata_clean[importer_metadata_columns]
    importer_metadata.to_parquet(current_dir / "metadata.parquet", index=False)
    content_clean.to_parquet(current_dir / "content.parquet", index=False)
    relationships[["doc_id", "other_doc_id", "relationship"]].to_parquet(
        current_dir / "relationships.parquet", index=False
    )
    documents.to_parquet(rag_dir / "law_documents.parquet", index=False)
    relationships.to_parquet(rag_dir / "law_relationships.parquet", index=False)

    print("Writing RAG chunks in batches...", flush=True)
    chunk_path = rag_dir / "law_chunks.parquet"
    chunk_writer: pq.ParquetWriter | None = None
    chunk_batch: list[dict[str, Any]] = []
    chunk_rows = 0
    chunk_count_by_doc: dict[int, int] = {}

    def flush_chunks() -> None:
        nonlocal chunk_writer, chunk_batch
        if not chunk_batch:
            return
        table = pa.Table.from_pylist(chunk_batch)
        if chunk_writer is None:
            chunk_writer = pq.ParquetWriter(chunk_path, table.schema, compression="snappy")
        chunk_writer.write_table(table)
        chunk_batch = []

    for row in documents.itertuples(index=False):
        doc_id = int(row.document_id)
        header = row.document_context
        text = row.content_text or ""
        doc_chunk_count = 0
        for chunk_index, (start, end, chunk) in enumerate(chunk_text(text)):
            chunk_batch.append(
                {
                    "chunk_id": f"{doc_id}:{chunk_index}",
                    "document_id": doc_id,
                    "chunk_index": chunk_index,
                    "char_start": start,
                    "char_end": end,
                    "chunk_text": chunk,
                    "retrieval_text": f"{header}\n\nNội dung đoạn:\n{chunk}",
                    "title": row.title,
                    "external_source": row.external_source,
                    "external_docid": row.external_docid,
                    "source_url": row.source_url,
                    "so_ky_hieu": row.so_ky_hieu,
                    "loai_van_ban": row.loai_van_ban,
                    "validity_code": row.validity_code,
                    "tinh_trang_hieu_luc": row.tinh_trang_hieu_luc,
                    "ngay_ban_hanh_iso": row.ngay_ban_hanh_iso,
                    "ngay_co_hieu_luc_iso": row.ngay_co_hieu_luc_iso,
                    "ngay_het_hieu_luc_iso": row.ngay_het_hieu_luc_iso,
                    "co_quan_ban_hanh": row.co_quan_ban_hanh,
                    "pham_vi": row.pham_vi,
                    "nganh": row.nganh,
                    "linh_vuc": row.linh_vuc,
                }
            )
            doc_chunk_count += 1
            chunk_rows += 1
            if len(chunk_batch) >= CHUNK_WRITE_BATCH_SIZE:
                flush_chunks()
        if doc_chunk_count:
            chunk_count_by_doc[doc_id] = doc_chunk_count
    flush_chunks()
    if chunk_writer is not None:
        chunk_writer.close()
    elif chunk_path.exists():
        chunk_path.unlink()

    print("Writing quality report...", flush=True)
    text_lengths_series = pd.Series(list(text_lengths.values()))
    chunk_counts = pd.Series(list(chunk_count_by_doc.values()), dtype="int64")
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "legacy_excluded": True,
        "source_rows": {
            "metadata": int(len(metadata)),
            "content": int(len(content)),
            "relationships": int(original_relationship_rows),
        },
        "output_rows": {
            "current_metadata": int(len(importer_metadata)),
            "current_content": int(len(content_clean)),
            "current_relationships": int(len(relationships)),
            "rag_documents": int(len(documents)),
            "rag_relationships": int(len(relationships)),
            "rag_chunks": int(chunk_rows),
        },
        "join_quality": {
            "metadata_unique_ids": int(metadata_clean["id"].nunique()),
            "content_unique_ids": int(content_clean["id"].nunique()),
            "content_missing_metadata": int(len(content_ids - metadata_ids)),
            "metadata_missing_content": int(len(metadata_ids - content_ids)),
            "relationship_doc_missing_metadata": relationship_doc_missing,
            "relationship_other_doc_missing_metadata": relationship_other_missing,
        },
        "relationship_cleanup": {
            "duplicate_rows_removed": duplicate_relationship_rows,
            "self_links_removed": self_relationship_rows,
            "relationship_labels": relationships["relationship"].value_counts(dropna=False).to_dict(),
        },
        "content_quality": {
            "empty_text_documents": int((documents["content_text_length"] == 0).sum()),
            "short_text_lt_80_documents": int((documents["content_text_length"] < 80).sum()),
            "bad_documents_csv": str(audit_dir / "bad_documents.csv"),
            "text_length_min": int(text_lengths_series.min()),
            "text_length_median": int(text_lengths_series.median()),
            "text_length_mean": float(round(text_lengths_series.mean(), 2)),
            "text_length_p95": int(text_lengths_series.quantile(0.95)),
            "text_length_max": int(text_lengths_series.max()),
        },
        "metadata_quality": {
            "null_counts": metadata_clean.isna().sum().astype(int).to_dict(),
            "validity_counts": metadata_clean["tinh_trang_hieu_luc"].fillna("").value_counts().to_dict(),
            "document_type_counts_top20": metadata_clean["loai_van_ban"].fillna("").value_counts().head(20).to_dict(),
            "invalid_date_counts": {
                "ngay_ban_hanh": int(metadata_clean["ngay_ban_hanh_iso"].isna().sum()),
                "ngay_co_hieu_luc": int(metadata_clean["ngay_co_hieu_luc_iso"].isna().sum()),
                "ngay_het_hieu_luc": int(
                    metadata_clean["ngay_het_hieu_luc"].notna().sum()
                    - metadata_clean["ngay_het_hieu_luc_iso"].notna().sum()
                ),
            },
        },
        "chunking": {
            "chunk_size": CHUNK_SIZE,
            "chunk_overlap": CHUNK_OVERLAP,
            "documents_with_chunks": int(chunk_counts.shape[0]),
            "documents_without_chunks": int(len(documents) - chunk_counts.shape[0]),
            "chunks_min_per_document": int(chunk_counts.min()) if not chunk_counts.empty else 0,
            "chunks_median_per_document": float(chunk_counts.median()) if not chunk_counts.empty else 0,
            "chunks_mean_per_document": float(round(chunk_counts.mean(), 2)) if not chunk_counts.empty else 0,
            "chunks_max_per_document": int(chunk_counts.max()) if not chunk_counts.empty else 0,
        },
    }
    (audit_dir / "data_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_readme(output_dir, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dataset/vietnamese_legal_documents/data_usable"),
    )
    args = parser.parse_args()
    report = prepare(args.input_dir, args.output_dir)
    print(json.dumps(report["output_rows"], ensure_ascii=False, indent=2))
    print(f"Quality report: {args.output_dir / 'audit' / 'data_quality_report.json'}")


if __name__ == "__main__":
    main()
