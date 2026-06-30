from __future__ import annotations

import argparse
import logging
import sys
import time

from law_crawler.audit import audit_vbpl_api_400_failures
from law_crawler.config import load_settings
from law_crawler.db import create_db_engine, create_session_factory, init_db
from law_crawler.discovery import discover_from_seed_file, discover_from_sitemap
from law_crawler.exporter import DEFAULT_EXPORT_BATCH_SIZE, export_parquet
from law_crawler.fetcher import extract_document_id, fetch_vbpl_document, fetch_vbpl_document_by_id
from law_crawler.parser import parse_document_html
from law_crawler.quality import requeue_quality_issues
from law_crawler.repository import persist_parsed_document, persist_pdf_review_document
from law_crawler.site_crawler import crawl_pending_jobs, enqueue_discovered_urls


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("mysql.connector").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(prog="vn-law-crawler")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Create crawler tables if they do not exist.")
    crawl_url = subparsers.add_parser("crawl-url", help="Fetch, parse, and persist one vbpl.vn full-text URL.")
    crawl_url.add_argument("url")
    crawl_url.add_argument(
        "--api",
        action="store_true",
        help="Fetch content from the public VBPL API using the document id in the URL.",
    )

    discover = subparsers.add_parser("discover-site", help="Discover document URLs from VBPL sitemap or a seed file.")
    discover.add_argument("--sitemap-url", default="https://vbpl.vn/sitemap.xml")
    discover.add_argument("--seed-file")
    discover.add_argument("--limit", type=int)
    discover.add_argument("--flush-every", type=int, default=1000)
    discover.add_argument("--progress-every", type=int, default=5000)

    crawl_site = subparsers.add_parser("crawl-site", help="Discover and crawl VBPL documents with resumable crawl jobs.")
    crawl_site.add_argument("--sitemap-url", default="https://vbpl.vn/sitemap.xml")
    crawl_site.add_argument("--seed-file")
    crawl_site.add_argument("--discover-limit", type=int)
    crawl_site.add_argument("--crawl-limit", type=int)
    crawl_site.add_argument("--max-attempts", type=int, default=3)
    crawl_site.add_argument("--delay-seconds", type=float, default=0.5)
    crawl_site.add_argument("--progress-every", type=int, default=5000)
    crawl_site.add_argument(
        "--retry-skipped",
        action="store_true",
        help="Retry jobs previously marked SKIPPED, for example after fetch/parser fixes.",
    )
    crawl_site.add_argument(
        "--retry-exhausted",
        action="store_true",
        help="Retry FAILED jobs even when their attempts already reached --max-attempts.",
    )
    crawl_site.add_argument(
        "--retry-previous",
        action="store_true",
        help="Retry both SKIPPED jobs and exhausted FAILED jobs from previous runs.",
    )
    crawl_site.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Only process already queued crawl jobs.",
    )

    export = subparsers.add_parser("export-parquet", help="Export crawled data into local Parquet files.")
    export.add_argument("--output-dir", default="data_usable/current")
    export.add_argument(
        "--all-versions",
        action="store_true",
        help="Export every stored document version instead of only current versions.",
    )
    export.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_EXPORT_BATCH_SIZE,
        help=f"Rows to hold in memory per Parquet write batch. Default: {DEFAULT_EXPORT_BATCH_SIZE}.",
    )
    export.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress export progress messages.",
    )
    export.add_argument(
        "--tables",
        nargs="+",
        choices=["metadata", "context", "relationships", "anchors", "pdf_review"],
        help="Export only selected tables. Useful for resuming after earlier tables finished.",
    )
    requeue_quality = subparsers.add_parser(
        "requeue-quality-issues",
        help="Requeue already crawled documents with parser-quality issues for a cleanup crawl.",
    )
    requeue_quality.add_argument(
        "--execute",
        action="store_true",
        help="Apply requeue updates. Without this flag, only prints affected counts.",
    )
    requeue_quality.add_argument("--empty-content-max-chars", type=int, default=0)
    requeue_quality.add_argument("--no-article-min-chars", type=int, default=500)
    requeue_quality.add_argument("--long-title-min-chars", type=int, default=1000)
    audit_vbpl_400 = subparsers.add_parser(
        "audit-vbpl-400-failures",
        help="List crawl jobs that failed with VBPL API 400 Bad Request errors.",
    )
    audit_vbpl_400.add_argument("--limit", type=int, default=100)
    audit_vbpl_400.add_argument(
        "--requeue",
        action="store_true",
        help="Prepare matching jobs to be retried from the improved fallback fetcher.",
    )
    audit_vbpl_400.add_argument(
        "--execute",
        action="store_true",
        help="Apply the requeue update. Without this flag, the command is read-only.",
    )

    args = parser.parse_args(argv)
    settings = load_settings()
    engine = create_db_engine(settings)

    if args.command == "init-db":
        init_db(engine)
        return 0

    if args.command == "crawl-url":
        if args.api:
            fetched = fetch_vbpl_document_by_id(extract_document_id(args.url), args.url, settings)
        else:
            fetched = fetch_vbpl_document(args.url, settings)
        session_factory = create_session_factory(engine)
        with session_factory.begin() as session:
            if fetched.content_source == "PDF_TEXT":
                review_document = persist_pdf_review_document(
                    session,
                    document_id=fetched.document_id,
                    source_url=fetched.source_url,
                    html=fetched.html,
                    pdf_file_name=fetched.pdf_file_name,
                    title=fetched.title,
                    document_number=fetched.document_number,
                    document_type=fetched.document_type,
                    issued_date=fetched.issued_date,
                    effective_date=fetched.effective_date,
                    expired_date=fetched.expired_date,
                    validity_status=fetched.validity_status,
                    issuing_authority=fetched.issuing_authority,
                )
                print(
                    f"Stored PDF review document_id={review_document.document_id} "
                    f"file={review_document.pdf_file_name}"
                )
                return 0
            parsed = parse_document_html(fetched.html)
            version = persist_parsed_document(
                session,
                document_id=fetched.document_id,
                source_url=fetched.source_url,
                parsed=parsed,
                title=fetched.title,
                document_number=fetched.document_number,
                document_type=fetched.document_type,
                issued_date=fetched.issued_date,
                effective_date=fetched.effective_date,
                expired_date=fetched.expired_date,
                validity_status=fetched.validity_status,
                issuing_authority=fetched.issuing_authority,
                relationships=fetched.relationships,
            )
            print(
                f"Persisted document_id={fetched.document_id} version_id={version.id} "
                f"articles={len(parsed.articles)} tables={len(parsed.tables)} "
                f"forms={len(parsed.forms)} annexes={len(parsed.annexes)}"
            )
        return 0

    if args.command == "discover-site":
        session_factory = create_session_factory(engine)
        enqueued = _discover_and_enqueue(args, settings, session_factory)
        print(f"Discovered and enqueued {enqueued} document URLs")
        return 0

    if args.command == "crawl-site":
        session_factory = create_session_factory(engine)
        discovered_count = 0
        if not args.skip_discovery:
            discovered = _discover(args, settings, limit=args.discover_limit)
            with session_factory.begin() as session:
                discovered_count = enqueue_discovered_urls(session, discovered)
        summary = crawl_pending_jobs(
            session_factory,
            settings,
            limit=args.crawl_limit,
            max_attempts=args.max_attempts,
            delay_seconds=args.delay_seconds,
            retry_skipped=args.retry_skipped or args.retry_previous,
            retry_exhausted=args.retry_exhausted or args.retry_previous,
        )
        print(
            f"discovered={discovered_count} crawled={summary.crawled} "
            f"pdf_review={summary.pdf_review} skipped={summary.skipped} failed={summary.failed}"
        )
        return 0

    if args.command == "export-parquet":
        summary = export_parquet(
            engine,
            args.output_dir,
            current_only=not args.all_versions,
            batch_size=args.batch_size,
            progress=not args.quiet,
            tables=set(args.tables) if args.tables else None,
        )
        print(
            f"Exported parquet files to {summary.output_dir}: "
            f"metadata={summary.metadata_rows} context={summary.context_rows} "
            f"relationships={summary.relationship_rows} anchors={summary.anchor_rows} "
            f"pdf_review={summary.pdf_review_rows}"
        )
        return 0

    if args.command == "requeue-quality-issues":
        summary = requeue_quality_issues(
            engine,
            execute=args.execute,
            empty_content_max_chars=args.empty_content_max_chars,
            no_article_min_chars=args.no_article_min_chars,
            long_title_min_chars=args.long_title_min_chars,
        )
        mode = "dry-run" if summary.dry_run else "executed"
        print(
            f"{mode}: empty_content_docs={summary.empty_content_docs} "
            f"no_article_docs={summary.no_article_docs} "
            f"long_title_docs={summary.long_title_docs} "
            f"requeued_jobs={summary.requeued_jobs}"
        )
        return 0

    if args.command == "audit-vbpl-400-failures":
        summary = audit_vbpl_api_400_failures(
            engine,
            limit=max(1, args.limit),
            requeue=args.requeue,
            execute=args.execute,
        )
        mode = "dry-run" if summary.dry_run else "executed"
        print(
            f"{mode}: vbpl_api_400_failures={summary.total_matches} "
            f"requeued_jobs={summary.requeued_jobs}"
        )
        for row in summary.rows:
            print(
                f"job_id={row.job_id} document_id={row.document_id} status={row.status} "
                f"attempts={row.attempts} updated_at={row.updated_at} source_url={row.source_url}"
            )
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


def _discover(args: argparse.Namespace, settings, limit: int | None = None):
    if getattr(args, "seed_file", None):
        discovered = discover_from_seed_file(args.seed_file)
        return discovered[:limit] if limit is not None else discovered
    return discover_from_sitemap(
        args.sitemap_url,
        settings,
        limit=limit or getattr(args, "limit", None),
        progress_every=getattr(args, "progress_every", 5000),
    )


def _discover_and_enqueue(args: argparse.Namespace, settings, session_factory) -> int:
    if getattr(args, "seed_file", None):
        discovered = _discover(args, settings)
        with session_factory.begin() as session:
            return enqueue_discovered_urls(session, discovered)

    buffer = []
    total = 0
    flush_every = max(1, args.flush_every)

    def flush() -> None:
        nonlocal total
        if not buffer:
            return
        _enqueue_with_retry(session_factory, list(buffer))
        total += len(buffer)
        print(f"Enqueued {total} discovered URLs so far", flush=True)
        buffer.clear()

    def on_discovered(discovered) -> None:
        buffer.append(discovered)
        if len(buffer) >= flush_every:
            flush()

    print(f"Starting sitemap discovery from {args.sitemap_url}", flush=True)
    discover_from_sitemap(
        args.sitemap_url,
        settings,
        limit=args.limit,
        on_discovered=on_discovered,
        progress_every=args.progress_every,
    )
    flush()
    return total


def _enqueue_with_retry(session_factory, discovered, *, attempts: int = 5) -> None:
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with session_factory.begin() as session:
                enqueue_discovered_urls(session, discovered)
            return
        except Exception as exc:
            last_error = exc
            if attempt == attempts:
                break
            sleep_seconds = min(30, 2 ** attempt)
            print(
                f"MySQL enqueue failed on attempt {attempt}/{attempts}; "
                f"retrying in {sleep_seconds}s: {exc}",
                flush=True,
            )
            try:
                session_factory.kw["bind"].dispose()
            except Exception:
                pass
            time.sleep(sleep_seconds)
    raise last_error


if __name__ == "__main__":
    sys.exit(main())
