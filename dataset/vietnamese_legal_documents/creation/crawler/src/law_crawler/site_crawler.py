from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import DBAPIError
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker

from law_crawler.config import Settings
from law_crawler.discovery import DiscoveredUrl
from law_crawler.fetcher import FetchError, fetch_vbpl_document_by_id
from law_crawler.models import CrawlJob, CrawlStatus
from law_crawler.parser import parse_document_html
from law_crawler.repository import persist_parsed_document, persist_pdf_review_document, upsert_crawl_job


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrawlRunSummary:
    discovered: int = 0
    crawled: int = 0
    pdf_review: int = 0
    skipped: int = 0
    failed: int = 0


def enqueue_discovered_urls(
    session: Session,
    discovered_urls: list[DiscoveredUrl],
) -> int:
    for discovered in discovered_urls:
        upsert_crawl_job(session, source_url=discovered.url, document_id=discovered.document_id)
    return len(discovered_urls)


def crawl_pending_jobs(
    session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    limit: int | None,
    max_attempts: int,
    delay_seconds: float,
    retry_skipped: bool = False,
    retry_exhausted: bool = False,
) -> CrawlRunSummary:
    crawled = 0
    pdf_review = 0
    skipped = 0
    failed = 0

    while limit is None or crawled + pdf_review + skipped + failed < limit:
        job_row = _with_db_retry(
            session_factory,
            lambda session: _claim_next_job(
                session,
                max_attempts,
                retry_skipped=retry_skipped,
                retry_exhausted=retry_exhausted,
            ),
        )
        if job_row is None:
            break
        job_id, document_id, source_url = job_row

        if document_id is None:
            _with_db_retry(
                session_factory,
                lambda session: _update_job_status(session, job_id, CrawlStatus.SKIPPED, "Missing document id"),
            )
            skipped += 1
            continue

        try:
            fetched = fetch_vbpl_document_by_id(document_id, source_url, settings)
            def persist(session):
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
                    job = session.get(CrawlJob, job_id)
                    if job:
                        job.document_id = fetched.document_id
                        job.status = CrawlStatus.PDF_REVIEW
                        job.last_error = "PDF_TEXT_REQUIRES_MANUAL_REVIEW"
                        job.crawled_at = datetime.utcnow()
                    LOGGER.info(
                        "Stored PDF review document_id=%s file=%s",
                        review_document.document_id,
                        review_document.pdf_file_name,
                    )
                    return
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
                job = session.get(CrawlJob, job_id)
                if job:
                    job.document_id = fetched.document_id
                    job.status = CrawlStatus.CRAWLED
                    job.last_error = None
                    job.crawled_at = datetime.utcnow()
                LOGGER.info(
                    "Crawled document_id=%s version_id=%s articles=%s tables=%s",
                    fetched.document_id,
                    version.id,
                    len(parsed.articles),
                    len(parsed.tables),
                )
            _with_db_retry(session_factory, persist)
            if fetched.content_source == "PDF_TEXT":
                pdf_review += 1
            else:
                crawled += 1
        except FetchError as exc:
            skipped += 1
            _mark_job(session_factory, job_id, CrawlStatus.SKIPPED, str(exc))
        except Exception as exc:
            failed += 1
            LOGGER.exception("Failed crawling document_id=%s source_url=%s", document_id, source_url)
            _mark_job(session_factory, job_id, CrawlStatus.FAILED, str(exc))

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return CrawlRunSummary(crawled=crawled, pdf_review=pdf_review, skipped=skipped, failed=failed)


def _mark_job(
    session_factory: sessionmaker[Session],
    job_id: int,
    status: CrawlStatus,
    error: str,
) -> None:
    _with_db_retry(
        session_factory,
        lambda session: _update_job_status(session, job_id, status, error[:4000]),
    )


def _claim_next_job(
    session: Session,
    max_attempts: int,
    *,
    retry_skipped: bool = False,
    retry_exhausted: bool = False,
) -> tuple[int, int | None, str] | None:
    retryable_statuses = [
        CrawlJob.status == CrawlStatus.DISCOVERED,
        and_(CrawlJob.status == CrawlStatus.FAILED, CrawlJob.attempts < max_attempts),
    ]
    if retry_exhausted:
        retryable_statuses.append(CrawlJob.status == CrawlStatus.FAILED)
    if retry_skipped:
        retryable_statuses.append(CrawlJob.status == CrawlStatus.SKIPPED)

    job = session.scalar(
        select(CrawlJob)
        .where(or_(*retryable_statuses))
        .order_by(CrawlJob.updated_at.asc(), CrawlJob.id.asc())
        .limit(1)
    )
    if job is None:
        return None
    job.attempts += 1
    return job.id, job.document_id, job.source_url


def _update_job_status(session: Session, job_id: int, status: CrawlStatus, error: str | None) -> None:
    job = session.get(CrawlJob, job_id)
    if job:
        job.status = status
        job.last_error = error
        job.crawled_at = datetime.utcnow()


def _with_db_retry(session_factory: sessionmaker[Session], operation, *, attempts: int = 5):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with session_factory.begin() as session:
                return operation(session)
        except DBAPIError as exc:
            last_error = exc
            if attempt == attempts:
                break
            sleep_seconds = min(30, 2 ** attempt)
            LOGGER.warning(
                "MySQL operation failed on attempt %s/%s; retrying in %ss: %s",
                attempt,
                attempts,
                sleep_seconds,
                exc,
            )
            try:
                session_factory.kw["bind"].dispose()
            except Exception:
                pass
            time.sleep(sleep_seconds)
    raise last_error
