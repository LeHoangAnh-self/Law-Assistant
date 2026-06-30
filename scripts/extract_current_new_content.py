#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract document-level content from current_new/context.parquet into "
            "content.parquet so law-service does not have to scan the full context table."
        )
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data_usable/current_new"),
        help="Directory containing context.parquet.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("data_usable/current_new/content.parquet"),
        help="Output Parquet file consumed by law-service importer.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8192,
        help="Scan batch size. Keep moderate for low RAM pressure.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context_file = args.input_dir / "context.parquet"
    if not context_file.is_file():
        raise FileNotFoundError(f"Missing context file: {context_file}")

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    if args.output_file.exists():
        args.output_file.unlink()

    dataset = ds.dataset(context_file, format="parquet")
    scanner = dataset.scanner(
        columns=["document_id", "content_html", "content_text", "context_type"],
        filter=ds.field("context_type") == "DOCUMENT",
        batch_size=args.batch_size,
    )

    output_schema = pa.schema(
        [
            ("document_id", pa.int64()),
            ("content_html", pa.string()),
            ("content_text", pa.string()),
        ]
    )

    rows = 0
    with pq.ParquetWriter(args.output_file, output_schema, compression="zstd") as writer:
        for batch in scanner.to_batches():
            table = pa.Table.from_batches([batch])
            table = table.drop(["context_type"])
            html = table["content_html"]
            text = table["content_text"]
            html = pc.if_else(pc.is_null(html), text, html)
            table = table.set_column(
                table.schema.get_field_index("content_html"),
                "content_html",
                html,
            )
            table = table.select(["document_id", "content_html", "content_text"])
            writer.write_table(table.cast(output_schema))
            rows += table.num_rows

    print(f"Wrote {rows} rows to {args.output_file}")


if __name__ == "__main__":
    main()
