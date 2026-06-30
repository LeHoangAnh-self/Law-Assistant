from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable, Mapping
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import Engine, TextClause, text
from sqlalchemy.engine import Connection


DEFAULT_EXPORT_BATCH_SIZE = 500


@dataclass(frozen=True)
class ExportSummary:
    output_dir: Path
    metadata_rows: int
    context_rows: int
    relationship_rows: int
    anchor_rows: int
    pdf_review_rows: int


@dataclass(frozen=True)
class ExportQuery:
    query: TextClause
    cursor_column: str | None = None


def export_parquet(
    engine: Engine,
    output_dir: str | Path,
    *,
    current_only: bool = True,
    batch_size: int = DEFAULT_EXPORT_BATCH_SIZE,
    progress: bool = False,
    tables: set[str] | None = None,
) -> ExportSummary:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    selected_tables = tables or {"metadata", "context", "relationships", "anchors", "pdf_review"}

    with engine.connect() as connection:
        metadata_rows = (
            _write_query_parquet(
                connection,
                output_path / "metadata.parquet",
                [_metadata_query(current_only)],
                _metadata_schema(),
                label="metadata",
                batch_size=batch_size,
                progress=progress,
            )
            if "metadata" in selected_tables
            else _existing_parquet_rows(output_path / "metadata.parquet")
        )
        context_rows = (
            _write_query_parquet(
                connection,
                output_path / "context.parquet",
                _context_queries(current_only),
                _context_schema(),
                label="context",
                batch_size=batch_size,
                progress=progress,
            )
            if "context" in selected_tables
            else _existing_parquet_rows(output_path / "context.parquet")
        )
        relationship_rows = (
            _write_query_parquet(
                connection,
                output_path / "relationships.parquet",
                [_relationships_query()],
                _relationships_schema(),
                label="relationships",
                batch_size=batch_size,
                progress=progress,
            )
            if "relationships" in selected_tables
            else _existing_parquet_rows(output_path / "relationships.parquet")
        )
        anchor_rows = (
            _write_query_parquet(
                connection,
                output_path / "anchors.parquet",
                [_anchors_query(current_only)],
                _anchors_schema(),
                label="anchors",
                batch_size=batch_size,
                progress=progress,
            )
            if "anchors" in selected_tables
            else _existing_parquet_rows(output_path / "anchors.parquet")
        )
        pdf_review_rows = (
            _write_query_parquet(
                connection,
                output_path / "pdf_review.parquet",
                [_pdf_review_query()],
                _pdf_review_schema(),
                label="pdf_review",
                batch_size=batch_size,
                progress=progress,
            )
            if "pdf_review" in selected_tables
            else _existing_parquet_rows(output_path / "pdf_review.parquet")
        )

    return ExportSummary(
        output_dir=output_path,
        metadata_rows=metadata_rows,
        context_rows=context_rows,
        relationship_rows=relationship_rows,
        anchor_rows=anchor_rows,
        pdf_review_rows=pdf_review_rows,
    )


def _write_query_parquet(
    connection: Connection,
    path: Path,
    queries: Iterable[ExportQuery],
    schema: pa.Schema,
    *,
    label: str,
    batch_size: int,
    progress: bool,
) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.unlink(missing_ok=True)
    row_count = 0
    writer: pq.ParquetWriter | None = None

    try:
        if progress:
            _print_progress(f"Exporting {label}...")
        next_progress = 10_000
        for export_query in queries:
            page_query = export_query.query if export_query.cursor_column else _paged_query(export_query.query)
            offset = 0
            last_cursor = 0
            while True:
                params = {"limit": batch_size}
                if export_query.cursor_column:
                    params["last_cursor"] = last_cursor
                else:
                    params["offset"] = offset
                batch = list(
                    connection.execute(
                        page_query,
                        params,
                    ).mappings()
                )
                if not batch:
                    break
                writer = _write_parquet_batch(tmp_path, batch, schema, writer)
                row_count += len(batch)
                if export_query.cursor_column:
                    last_cursor = batch[-1][export_query.cursor_column]
                if progress and row_count >= next_progress:
                    _print_progress(f"Exporting {label}: {row_count:,} rows")
                    next_progress += 10_000
                if len(batch) < batch_size:
                    break
                offset += batch_size

        if writer is None:
            _write_parquet(tmp_path, [], schema)
        else:
            writer.close()
            writer = None
        tmp_path.replace(path)
        if progress:
            _print_progress(f"Exported {label}: {row_count:,} rows")
    finally:
        if writer is not None:
            writer.close()
        tmp_path.unlink(missing_ok=True)

    return row_count


def _existing_parquet_rows(path: Path) -> int:
    if not path.exists():
        return 0
    return pq.ParquetFile(path).metadata.num_rows


def _print_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _paged_query(query: TextClause) -> TextClause:
    return text(
        f"""
        select *
        from (
            {query.text}
        ) as export_rows
        limit :limit offset :offset
        """
    )


def _write_parquet_batch(
    path: Path,
    rows: list[Mapping],
    schema: pa.Schema,
    writer: pq.ParquetWriter | None,
) -> pq.ParquetWriter:
    table = _rows_to_table(rows, schema)
    if writer is None:
        writer = pq.ParquetWriter(path, schema, compression="snappy")
    writer.write_table(table)
    return writer


def _write_parquet(path: Path, rows: list[Mapping], schema: pa.Schema) -> None:
    table = _rows_to_table(rows, schema)
    pq.write_table(table, path, compression="snappy")


def _rows_to_table(rows: list[Mapping], schema: pa.Schema) -> pa.Table:
    rows = [_normalize_row(row, schema) for row in rows]
    return pa.Table.from_pylist(rows, schema=schema)


def _normalize_row(row: Mapping, schema: pa.Schema) -> dict:
    normalized = {}
    for field in schema:
        value = row.get(field.name)
        if value is not None and pa.types.is_boolean(field.type):
            value = bool(value)
        normalized[field.name] = value
    return normalized


def _metadata_query(current_only: bool):
    version_filter = "where v.is_current = true" if current_only else ""
    return ExportQuery(
        text(
        f"""
        select
            d.id as document_id,
            v.id as version_id,
            v.version_label,
            v.is_current,
            d.title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            d.issued_date,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.expired_date, d.expired_date) as expired_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            d.source,
            v.source_url,
            v.source_hash,
            v.crawled_at
        from legal_document_versions v
        join legal_documents d on d.id = v.document_id
        {version_filter}
        order by d.id, v.id
        """
        )
    )


def _context_queries(current_only: bool):
    version_filter = "and v.is_current = true" if current_only else ""
    return [
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'DOCUMENT' as context_type,
            d.id as context_id,
            'document' as stable_anchor,
            0 as order_index,
            cast(null as char) as article_number,
            cast(null as signed) as article_occurrence,
            cast(null as char) as clause_number,
            cast(null as signed) as clause_occurrence,
            cast(null as char) as point_label,
            cast(null as signed) as point_occurrence,
            d.title as heading,
            c.content_text,
            c.content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_contents c
        join legal_document_versions v on v.id = c.version_id
        join legal_documents d on d.id = c.document_id
        where 1=1 {version_filter}
        """
            )
        ),
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'ARTICLE' as context_type,
            a.id as context_id,
            a.stable_anchor,
            a.order_index,
            a.article_number,
            a.article_occurrence,
            cast(null as char) as clause_number,
            cast(null as signed) as clause_occurrence,
            cast(null as char) as point_label,
            cast(null as signed) as point_occurrence,
            a.title as heading,
            a.content_text,
            a.content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_articles a
        join legal_document_versions v on v.id = a.version_id
        join legal_documents d on d.id = a.document_id
        where 1=1 {version_filter}
        """
            )
        ),
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'CLAUSE' as context_type,
            c.id as context_id,
            c.stable_anchor,
            c.order_index,
            a.article_number,
            a.article_occurrence,
            c.clause_number,
            c.clause_occurrence,
            cast(null as char) as point_label,
            cast(null as signed) as point_occurrence,
            concat('Điều ', a.article_number, ', khoản ', c.clause_number) as heading,
            c.content_text,
            c.content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_clauses c
        join legal_document_articles a on a.id = c.article_id
        join legal_document_versions v on v.id = a.version_id
        join legal_documents d on d.id = a.document_id
        where 1=1 {version_filter}
        """
            )
        ),
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'POINT' as context_type,
            p.id as context_id,
            p.stable_anchor,
            p.order_index,
            a.article_number,
            a.article_occurrence,
            c.clause_number,
            c.clause_occurrence,
            p.point_label,
            p.point_occurrence,
            concat('Điều ', a.article_number, ', khoản ', c.clause_number, ', điểm ', p.point_label) as heading,
            p.content_text,
            p.content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_points p
        join legal_document_clauses c on c.id = p.clause_id
        join legal_document_articles a on a.id = c.article_id
        join legal_document_versions v on v.id = a.version_id
        join legal_documents d on d.id = a.document_id
        where 1=1 {version_filter}
        """
            )
        ),
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'TABLE' as context_type,
            t.id as context_id,
            t.stable_anchor,
            t.order_index,
            a.article_number,
            a.article_occurrence,
            cast(null as char) as clause_number,
            cast(null as signed) as clause_occurrence,
            cast(null as char) as point_label,
            cast(null as signed) as point_occurrence,
            t.caption as heading,
            t.text as content_text,
            t.html as content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_tables t
        join legal_document_versions v on v.id = t.version_id
        join legal_documents d on d.id = v.document_id
        left join legal_document_articles a on a.id = t.article_id
        where 1=1 {version_filter}
        """
            )
        ),
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'FORM' as context_type,
            f.id as context_id,
            f.stable_anchor,
            f.id as order_index,
            cast(null as char) as article_number,
            cast(null as signed) as article_occurrence,
            cast(null as char) as clause_number,
            cast(null as signed) as clause_occurrence,
            cast(null as char) as point_label,
            cast(null as signed) as point_occurrence,
            f.title as heading,
            f.text as content_text,
            f.html as content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_forms f
        join legal_document_versions v on v.id = f.version_id
        join legal_documents d on d.id = v.document_id
        where 1=1 {version_filter}
        """
            )
        ),
        ExportQuery(
            text(
            f"""
        select
            d.id as document_id,
            v.id as version_id,
            'ANNEX' as context_type,
            x.id as context_id,
            x.stable_anchor,
            x.order_index,
            cast(null as char) as article_number,
            cast(null as signed) as article_occurrence,
            cast(null as char) as clause_number,
            cast(null as signed) as clause_occurrence,
            cast(null as char) as point_label,
            cast(null as signed) as point_occurrence,
            x.title as heading,
            x.text as content_text,
            x.html as content_html,
            d.title as document_title,
            d.document_number,
            d.document_type,
            d.issuing_authority,
            coalesce(v.effective_date, d.effective_date) as effective_date,
            coalesce(v.validity_status, d.validity_status) as validity_status,
            v.source_url
        from legal_document_annexes x
        join legal_document_versions v on v.id = x.version_id
        join legal_documents d on d.id = v.document_id
        where 1=1 {version_filter}
        """
            )
        ),
    ]


def _relationships_query():
    return ExportQuery(
        text(
        """
        select
            id as relationship_id,
            document_id,
            related_document_id,
            relationship_type,
            source_text
        from legal_document_relationships
        order by document_id, related_document_id, relationship_type
        """
        )
    )


def _anchors_query(current_only: bool):
    version_filter = "and v.is_current = true" if current_only else ""
    return ExportQuery(
        text(
        f"""
        select
            a.id as export_cursor,
            d.id as document_id,
            v.id as version_id,
            a.stable_anchor,
            a.anchor_type,
            a.target_table,
            a.target_id,
            v.source_url
        from legal_document_anchors a force index (primary)
        straight_join legal_document_versions v on v.id = a.version_id
        straight_join legal_documents d on d.id = v.document_id
        where a.id > :last_cursor {version_filter}
        order by a.id
        limit :limit
        """
        ),
        cursor_column="export_cursor",
    )


def _pdf_review_query():
    return ExportQuery(
        text(
        """
        select
            document_id,
            source_url,
            title,
            document_number,
            document_type,
            issuing_authority,
            issued_date,
            effective_date,
            expired_date,
            validity_status,
            pdf_file_name,
            extracted_text,
            extracted_html,
            review_reason,
            created_at,
            updated_at
        from pdf_review_documents
        order by document_id
        """
        )
    )


def _metadata_schema() -> pa.Schema:
    return pa.schema(
        [
            ("document_id", pa.int64()),
            ("version_id", pa.int64()),
            ("version_label", pa.string()),
            ("is_current", pa.bool_()),
            ("title", pa.string()),
            ("document_number", pa.string()),
            ("document_type", pa.string()),
            ("issuing_authority", pa.string()),
            ("issued_date", pa.date32()),
            ("effective_date", pa.date32()),
            ("expired_date", pa.date32()),
            ("validity_status", pa.string()),
            ("source", pa.string()),
            ("source_url", pa.string()),
            ("source_hash", pa.string()),
            ("crawled_at", pa.timestamp("us")),
        ]
    )


def _context_schema() -> pa.Schema:
    return pa.schema(
        [
            ("document_id", pa.int64()),
            ("version_id", pa.int64()),
            ("context_type", pa.string()),
            ("context_id", pa.int64()),
            ("stable_anchor", pa.string()),
            ("order_index", pa.int64()),
            ("article_number", pa.string()),
            ("article_occurrence", pa.int64()),
            ("clause_number", pa.string()),
            ("clause_occurrence", pa.int64()),
            ("point_label", pa.string()),
            ("point_occurrence", pa.int64()),
            ("heading", pa.string()),
            ("content_text", pa.string()),
            ("content_html", pa.string()),
            ("document_title", pa.string()),
            ("document_number", pa.string()),
            ("document_type", pa.string()),
            ("issuing_authority", pa.string()),
            ("effective_date", pa.date32()),
            ("validity_status", pa.string()),
            ("source_url", pa.string()),
        ]
    )


def _relationships_schema() -> pa.Schema:
    return pa.schema(
        [
            ("relationship_id", pa.int64()),
            ("document_id", pa.int64()),
            ("related_document_id", pa.int64()),
            ("relationship_type", pa.string()),
            ("source_text", pa.string()),
        ]
    )


def _anchors_schema() -> pa.Schema:
    return pa.schema(
        [
            ("document_id", pa.int64()),
            ("version_id", pa.int64()),
            ("stable_anchor", pa.string()),
            ("anchor_type", pa.string()),
            ("target_table", pa.string()),
            ("target_id", pa.int64()),
            ("source_url", pa.string()),
        ]
    )


def _pdf_review_schema() -> pa.Schema:
    return pa.schema(
        [
            ("document_id", pa.int64()),
            ("source_url", pa.string()),
            ("title", pa.string()),
            ("document_number", pa.string()),
            ("document_type", pa.string()),
            ("issuing_authority", pa.string()),
            ("issued_date", pa.date32()),
            ("effective_date", pa.date32()),
            ("expired_date", pa.date32()),
            ("validity_status", pa.string()),
            ("pdf_file_name", pa.string()),
            ("extracted_text", pa.string()),
            ("extracted_html", pa.string()),
            ("review_reason", pa.string()),
            ("created_at", pa.timestamp("us")),
            ("updated_at", pa.timestamp("us")),
        ]
    )
