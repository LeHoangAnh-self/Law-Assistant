from __future__ import annotations

import argparse
import logging
import sys

from qna_crawler.config import load_settings
from qna_crawler.crawler import crawl_bachkhoaluat_government_qna
from qna_crawler.db import create_db_engine, create_engine_from_url, create_session_factory, init_db
from qna_crawler.exporter import DEFAULT_EXPORT_BATCH_SIZE, export_government_qna_parquet
from qna_crawler.retrieval_audit import QdrantPayloadClient, audit_qna_retrieval_readiness


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
    crawl.add_argument(
        "--discovery-mode",
        choices=["listing", "id-range"],
        default="listing",
        help="Use capped listing API or direct detail-ID scanning.",
    )
    crawl.add_argument(
        "--id-start",
        type=int,
        help="First detail id to scan in id-range mode. Defaults to latest Q&A id from listing.",
    )
    crawl.add_argument(
        "--id-end",
        type=int,
        help="Last detail id to scan in id-range mode. Defaults to 1.",
    )
    crawl.add_argument(
        "--max-consecutive-misses",
        type=int,
        help="Stop id-range scan after this many consecutive missing or non-Q&A IDs.",
    )
    crawl.add_argument("--delay-seconds", type=float, default=0.25)
    crawl.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print crawl progress every N processed items. Use 0 to disable progress.",
    )
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

    audit = subparsers.add_parser(
        "audit-retrieval-readiness",
        help="Audit Q&A citation coverage against the Qdrant retrieval index.",
    )
    audit.add_argument("--qdrant-url", default="http://localhost:6333")
    audit.add_argument("--qdrant-collection", default="legal_document_chunks")
    audit.add_argument("--qdrant-timeout-seconds", type=float, default=30.0)
    audit.add_argument("--limit", type=int, help="Only audit the first N citation rows.")
    audit.add_argument("--output-jsonl", help="Write per-citation audit rows as JSONL.")
    audit.add_argument(
        "--progress-every",
        type=int,
        default=500,
        help="Print audit progress every N citations. Use 0 to disable progress.",
    )

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
            progress_every=args.progress_every,
            discovery_mode=args.discovery_mode,
            id_start=args.id_start,
            id_end=args.id_end,
            max_consecutive_misses=args.max_consecutive_misses,
        )
        print(
            f"checked={summary.checked} fetched={summary.fetched} persisted={summary.persisted} "
            f"skipped={summary.skipped} failed={summary.failed} not_found={summary.not_found} "
            f"non_qna={summary.non_qna} citations={summary.citations} "
            f"matched_citations={summary.matched_citations} missing_citations={summary.missing_citations}"
        )
        return 0

    if args.command == "export-government-qna":
        init_db(qna_engine)
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

    if args.command == "audit-retrieval-readiness":
        init_db(qna_engine)
        try:
            summary = audit_qna_retrieval_readiness(
                qna_engine,
                QdrantPayloadClient(
                    args.qdrant_url,
                    args.qdrant_collection,
                    timeout_seconds=args.qdrant_timeout_seconds,
                ),
                limit=args.limit,
                output_jsonl=args.output_jsonl,
                progress_every=args.progress_every,
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
        print(
            f"checked_citations={summary.checked_citations} "
            f"unmatched_document_db_citations={summary.unmatched_document_db_citations} "
            f"ready_citations={summary.ready_citations} "
            f"document_not_indexed={summary.document_not_indexed} "
            f"article_not_indexed={summary.article_not_indexed} "
            f"clause_not_indexed={summary.clause_not_indexed} "
            f"point_not_indexed={summary.point_not_indexed} "
            f"no_structural_refs={summary.no_structural_refs} "
            f"output_jsonl={summary.output_jsonl or ''}"
        )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
