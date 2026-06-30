from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import sys

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import Engine, TextClause, text
from sqlalchemy.engine import Connection


DEFAULT_EXPORT_BATCH_SIZE = 500


@dataclass(frozen=True)
class ExportQuery:
    query: TextClause


@dataclass(frozen=True)
class GovernmentQnaExportSummary:
    output_dir: Path
    qna_rows: int
    citation_rows: int
    training_rows: int
    benchmark_rows: int


def export_government_qna_parquet(
    engine: Engine,
    output_dir: str | Path,
    *,
    batch_size: int = DEFAULT_EXPORT_BATCH_SIZE,
    progress: bool = False,
) -> GovernmentQnaExportSummary:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    with engine.connect() as connection:
        qna_rows = _write_query_parquet(
            connection,
            output_path / "government_qna.parquet",
            [ExportQuery(_qna_query())],
            _qna_schema(),
            label="government_qna",
            batch_size=batch_size,
            progress=progress,
        )
        citation_rows = _write_query_parquet(
            connection,
            output_path / "government_qna_citations.parquet",
            [ExportQuery(_citation_query())],
            _citation_schema(),
            label="government_qna_citations",
            batch_size=batch_size,
            progress=progress,
        )
        training_rows = _write_query_parquet(
            connection,
            output_path / "government_qna_training.parquet",
            [ExportQuery(_training_query())],
            _training_schema(),
            label="government_qna_training",
            batch_size=batch_size,
            progress=progress,
        )
        benchmark_rows = _write_query_parquet(
            connection,
            output_path / "government_qna_benchmark.parquet",
            [ExportQuery(_benchmark_query())],
            _benchmark_schema(),
            label="government_qna_benchmark",
            batch_size=batch_size,
            progress=progress,
        )

    return GovernmentQnaExportSummary(
        output_dir=output_path,
        qna_rows=qna_rows,
        citation_rows=citation_rows,
        training_rows=training_rows,
        benchmark_rows=benchmark_rows,
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
        for export_query in queries:
            page_query = _paged_query(export_query.query)
            offset = 0
            while True:
                batch = list(connection.execute(page_query, {"limit": batch_size, "offset": offset}).mappings())
                if not batch:
                    break
                writer = _write_parquet_batch(tmp_path, batch, schema, writer)
                row_count += len(batch)
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
    normalized_rows = []
    for row in rows:
        normalized = {}
        for field in schema:
            value = row.get(field.name)
            normalized[field.name] = None if value is None else str(value) if pa.types.is_string(field.type) else value
        normalized_rows.append(normalized)
    return pa.Table.from_pylist(normalized_rows, schema=schema)


def _print_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _qna_query():
    return text(
        """
        select
            id as qna_id,
            external_id,
            source_name,
            source_url,
            detail_url,
            original_url,
            title,
            question_text,
            answer_text,
            summary_text,
            responding_authority,
            category_name,
            tags,
            published_date,
            content_hash,
            citation_status,
            citation_count,
            matched_citation_count,
            missing_citation_count,
            crawled_at,
            updated_at
        from government_qna_items
        order by id
        """
    )


def _citation_query():
    return text(
        """
        select
            c.id as citation_id,
            c.qna_item_id as qna_id,
            q.external_id,
            q.title as qna_title,
            c.raw_text,
            c.document_number,
            c.document_title,
            c.article_refs,
            c.matched_document_id,
            c.match_status,
            c.match_reason,
            c.matched_document_title,
            c.matched_document_number,
            c.matched_document_source
        from government_qna_citations c
        join government_qna_items q on q.id = c.qna_item_id
        order by c.id
        """
    )


def _training_query():
    return text(
        """
        select
            id as qna_id,
            external_id,
            title,
            coalesce(question_text, summary_text, title) as prompt,
            answer_text as completion,
            responding_authority,
            category_name,
            tags,
            published_date,
            source_url,
            original_url,
            citation_status,
            citation_count,
            matched_citation_count,
            missing_citation_count
        from government_qna_items
        where answer_text is not null
          and length(answer_text) > 0
        order by id
        """
    )


def _benchmark_query():
    return text(
        """
        select
            q.id as qna_id,
            q.external_id,
            q.title,
            coalesce(q.question_text, q.summary_text, q.title) as question,
            q.answer_text as reference_answer,
            q.responding_authority,
            q.category_name,
            q.tags,
            q.published_date,
            q.source_url,
            q.original_url,
            c.id as citation_id,
            c.raw_text as cited_text,
            c.article_refs,
            c.matched_document_id as expected_document_id,
            c.matched_document_title as expected_document_title,
            c.matched_document_number as expected_document_number,
            c.matched_document_source as expected_document_source
        from government_qna_items q
        join government_qna_citations c on c.qna_item_id = q.id
        where q.answer_text is not null
          and length(q.answer_text) > 0
          and c.match_status = 'MATCHED'
        order by q.id, c.id
        """
    )


def _qna_schema() -> pa.Schema:
    return pa.schema(
        [
            ("qna_id", pa.int64()),
            ("external_id", pa.int64()),
            ("source_name", pa.string()),
            ("source_url", pa.string()),
            ("detail_url", pa.string()),
            ("original_url", pa.string()),
            ("title", pa.string()),
            ("question_text", pa.string()),
            ("answer_text", pa.string()),
            ("summary_text", pa.string()),
            ("responding_authority", pa.string()),
            ("category_name", pa.string()),
            ("tags", pa.string()),
            ("published_date", pa.string()),
            ("content_hash", pa.string()),
            ("citation_status", pa.string()),
            ("citation_count", pa.int64()),
            ("matched_citation_count", pa.int64()),
            ("missing_citation_count", pa.int64()),
            ("crawled_at", pa.string()),
            ("updated_at", pa.string()),
        ]
    )


def _citation_schema() -> pa.Schema:
    return pa.schema(
        [
            ("citation_id", pa.int64()),
            ("qna_id", pa.int64()),
            ("external_id", pa.int64()),
            ("qna_title", pa.string()),
            ("raw_text", pa.string()),
            ("document_number", pa.string()),
            ("document_title", pa.string()),
            ("article_refs", pa.string()),
            ("matched_document_id", pa.int64()),
            ("match_status", pa.string()),
            ("match_reason", pa.string()),
            ("matched_document_title", pa.string()),
            ("matched_document_number", pa.string()),
            ("matched_document_source", pa.string()),
        ]
    )


def _training_schema() -> pa.Schema:
    return pa.schema(
        [
            ("qna_id", pa.int64()),
            ("external_id", pa.int64()),
            ("title", pa.string()),
            ("prompt", pa.string()),
            ("completion", pa.string()),
            ("responding_authority", pa.string()),
            ("category_name", pa.string()),
            ("tags", pa.string()),
            ("published_date", pa.string()),
            ("source_url", pa.string()),
            ("original_url", pa.string()),
            ("citation_status", pa.string()),
            ("citation_count", pa.int64()),
            ("matched_citation_count", pa.int64()),
            ("missing_citation_count", pa.int64()),
        ]
    )


def _benchmark_schema() -> pa.Schema:
    return pa.schema(
        [
            ("qna_id", pa.int64()),
            ("external_id", pa.int64()),
            ("title", pa.string()),
            ("question", pa.string()),
            ("reference_answer", pa.string()),
            ("responding_authority", pa.string()),
            ("category_name", pa.string()),
            ("tags", pa.string()),
            ("published_date", pa.string()),
            ("source_url", pa.string()),
            ("original_url", pa.string()),
            ("citation_id", pa.int64()),
            ("cited_text", pa.string()),
            ("article_refs", pa.string()),
            ("expected_document_id", pa.int64()),
            ("expected_document_title", pa.string()),
            ("expected_document_number", pa.string()),
            ("expected_document_source", pa.string()),
        ]
    )
