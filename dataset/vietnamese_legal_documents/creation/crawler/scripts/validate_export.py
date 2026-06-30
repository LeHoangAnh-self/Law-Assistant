from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq
from sqlalchemy import text

from law_crawler.config import load_settings
from law_crawler.db import create_db_engine
from law_crawler.exporter import (
    _anchors_schema,
    _context_schema,
    _metadata_schema,
    _pdf_review_schema,
    _relationships_schema,
)


TABLES = {
    "metadata": ("metadata.parquet", _metadata_schema),
    "context": ("context.parquet", _context_schema),
    "relationships": ("relationships.parquet", _relationships_schema),
    "anchors": ("anchors.parquet", _anchors_schema),
    "pdf_review": ("pdf_review.parquet", _pdf_review_schema),
}


DB_COUNT_QUERIES = {
    "metadata": """
        select count(*)
        from legal_document_versions v
        where v.is_current = true
    """,
    "context": """
        select
            (select count(*) from legal_document_contents c join legal_document_versions v on v.id = c.version_id where v.is_current = true)
          + (select count(*) from legal_document_articles a join legal_document_versions v on v.id = a.version_id where v.is_current = true)
          + (select count(*) from legal_document_clauses c join legal_document_articles a on a.id = c.article_id join legal_document_versions v on v.id = a.version_id where v.is_current = true)
          + (select count(*) from legal_document_points p join legal_document_clauses c on c.id = p.clause_id join legal_document_articles a on a.id = c.article_id join legal_document_versions v on v.id = a.version_id where v.is_current = true)
          + (select count(*) from legal_document_tables t join legal_document_versions v on v.id = t.version_id where v.is_current = true)
          + (select count(*) from legal_document_forms f join legal_document_versions v on v.id = f.version_id where v.is_current = true)
          + (select count(*) from legal_document_annexes x join legal_document_versions v on v.id = x.version_id where v.is_current = true)
    """,
    "relationships": "select count(*) from legal_document_relationships",
    "anchors": """
        select count(*)
        from legal_document_anchors a
        join legal_document_versions v on v.id = a.version_id
        where v.is_current = true
    """,
    "pdf_review": "select count(*) from pdf_review_documents",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate exported Parquet dataset files.")
    parser.add_argument("--output-dir", default="data_usable/current_new")
    parser.add_argument("--compare-db", action="store_true", help="Compare exported row counts with the source DB.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    failures: list[str] = []
    warnings: list[str] = []
    row_counts: dict[str, int] = {}

    for table_name, (file_name, schema_factory) in TABLES.items():
        path = output_dir / file_name
        if not path.exists():
            failures.append(f"{file_name}: missing")
            continue
        if path.stat().st_size == 0:
            failures.append(f"{file_name}: empty file")
            continue

        try:
            parquet_file = pq.ParquetFile(path)
        except Exception as exc:
            failures.append(f"{file_name}: cannot read parquet metadata: {exc}")
            continue

        actual_schema = parquet_file.schema_arrow
        expected_schema = schema_factory()
        actual_names = actual_schema.names
        expected_names = expected_schema.names
        if actual_names != expected_names:
            failures.append(f"{file_name}: columns differ: expected {expected_names}, got {actual_names}")

        rows = parquet_file.metadata.num_rows
        row_counts[table_name] = rows
        print(f"{table_name:13} rows={rows:,} row_groups={parquet_file.metadata.num_row_groups:,} size={path.stat().st_size:,} bytes")

    _check_basic_integrity(output_dir, failures, warnings)

    if args.compare_db:
        _compare_db_counts(row_counts, failures)

    if failures:
        print("\nFAILED")
        for failure in failures:
            print(f"- {failure}")
    if warnings:
        print("\nWARNINGS")
        for warning in warnings:
            print(f"- {warning}")
    if failures:
        return 1

    print("\nOK")
    return 0


def _check_basic_integrity(output_dir: Path, failures: list[str], warnings: list[str]) -> None:
    metadata_path = output_dir / "metadata.parquet"
    context_path = output_dir / "context.parquet"
    anchors_path = output_dir / "anchors.parquet"

    if metadata_path.exists():
        metadata = pq.read_table(metadata_path, columns=["document_id", "version_id", "title", "is_current"])
        _require_no_null(metadata, "metadata.parquet", ["document_id", "version_id", "title", "is_current"], failures)
        _require_unique(metadata, "metadata.parquet", ["version_id"], failures)

    if context_path.exists():
        context = pq.read_table(context_path, columns=["document_id", "version_id", "context_type", "context_id", "content_text"])
        _require_no_null(context, "context.parquet", ["document_id", "version_id", "context_type", "context_id"], failures)
        empty_content = pc.sum(pc.or_(pc.is_null(context["content_text"]), pc.equal(pc.utf8_length(context["content_text"]), 0))).as_py()
        if empty_content:
            warnings.append(f"context.parquet: {empty_content:,} rows have null/empty content_text")

    if anchors_path.exists():
        anchors = pq.read_table(anchors_path, columns=["document_id", "version_id", "stable_anchor", "anchor_type", "target_table"])
        _require_no_null(anchors, "anchors.parquet", ["document_id", "version_id", "stable_anchor", "anchor_type", "target_table"], failures)


def _require_no_null(table, file_name: str, columns: list[str], failures: list[str]) -> None:
    for column in columns:
        nulls = table[column].null_count
        if nulls:
            failures.append(f"{file_name}: {column} has {nulls:,} nulls")


def _require_unique(table, file_name: str, columns: list[str], failures: list[str]) -> None:
    projected = table.select(columns)
    if projected.num_rows != len(projected.group_by(columns).aggregate([])):
        failures.append(f"{file_name}: duplicate values for {', '.join(columns)}")


def _compare_db_counts(row_counts: dict[str, int], failures: list[str]) -> None:
    engine = create_db_engine(load_settings())
    with engine.connect() as connection:
        for table_name, query in DB_COUNT_QUERIES.items():
            expected = int(connection.scalar(text(query)) or 0)
            actual = row_counts.get(table_name)
            print(f"{table_name:13} db_rows={expected:,}")
            if actual is not None and actual != expected:
                failures.append(f"{table_name}: exported {actual:,} rows, DB has {expected:,}")


if __name__ == "__main__":
    raise SystemExit(main())
