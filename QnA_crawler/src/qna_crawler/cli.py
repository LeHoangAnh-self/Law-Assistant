from __future__ import annotations

import argparse
import logging
import sys

from qna_crawler.config import load_settings
from qna_crawler.crawler import crawl_bachkhoaluat_government_qna
from qna_crawler.db import create_db_engine, create_engine_from_url, create_session_factory, init_db
from qna_crawler.exporter import DEFAULT_EXPORT_BATCH_SIZE, export_government_qna_parquet


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(prog="vn-law-qna-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create Q&A crawler tables if they do not exist.")

    crawl = subparsers.add_parser(
        "crawl-government-qna",
        help="Crawl government Q&A items for RAG benchmark and fine-tuning data.",
    )
    crawl.add_argument("--cookie-file", help="Browser cookie JSON exported for bachkhoaluat.vn.")
    crawl.add_argument(
        "--document-database-url",
        help="Read-only database URL containing legal_documents. Overrides QNA_CRAWLER_DOCUMENT_DATABASE_URL.",
    )
    crawl.add_argument("--limit", type=int, help="Maximum Q&A items to crawl.")
    crawl.add_argument("--delay-seconds", type=float, default=0.25)
    crawl.add_argument(
        "--allow-missing-answer",
        action="store_true",
        help="Persist Q&A metadata even when full answer text cannot be fetched.",
    )

    export = subparsers.add_parser(
        "export-government-qna",
        help="Export crawled government Q&A benchmark/fine-tuning data to Parquet.",
    )
    export.add_argument("--output-dir", default="../data_usable/government_qna")
    export.add_argument("--batch-size", type=int, default=DEFAULT_EXPORT_BATCH_SIZE)
    export.add_argument("--quiet", action="store_true")

    args = parser.parse_args(argv)
    settings = load_settings()
    qna_engine = create_db_engine(settings)

    if args.command == "init-db":
        init_db(qna_engine)
        return 0

    if args.command == "crawl-government-qna":
        document_database_url = args.document_database_url or settings.document_database_url
        if not document_database_url:
            raise RuntimeError(
                "QNA_CRAWLER_DOCUMENT_DATABASE_URL is required for crawl-government-qna "
                "so citations can be checked against the document database."
            )
        qna_session_factory = create_session_factory(qna_engine)
        document_session_factory = create_session_factory(create_engine_from_url(document_database_url))
        summary = crawl_bachkhoaluat_government_qna(
            qna_session_factory,
            document_session_factory,
            settings,
            cookie_file=args.cookie_file,
            limit=args.limit,
            delay_seconds=args.delay_seconds,
            require_answer=not args.allow_missing_answer,
        )
        print(
            f"fetched={summary.fetched} persisted={summary.persisted} skipped={summary.skipped} "
            f"failed={summary.failed} citations={summary.citations} "
            f"matched_citations={summary.matched_citations} missing_citations={summary.missing_citations}"
        )
        return 0

    if args.command == "export-government-qna":
        summary = export_government_qna_parquet(
            qna_engine,
            args.output_dir,
            batch_size=args.batch_size,
            progress=not args.quiet,
        )
        print(
            f"Exported government Q&A parquet files to {summary.output_dir}: "
            f"qna={summary.qna_rows} citations={summary.citation_rows} "
            f"training={summary.training_rows} benchmark={summary.benchmark_rows}"
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
