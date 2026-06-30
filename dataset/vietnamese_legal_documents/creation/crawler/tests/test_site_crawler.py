from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from law_crawler.models import CrawlJob, CrawlStatus
from law_crawler.site_crawler import _claim_next_job


def _session_factory():
    engine = create_engine("sqlite:///:memory:")
    CrawlJob.__table__.create(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _job(
    *,
    job_id: int,
    status: CrawlStatus,
    attempts: int,
    updated_at: datetime,
    document_id: int | None = None,
) -> CrawlJob:
    return CrawlJob(
        id=job_id,
        source_url=f"https://vbpl.vn/van-ban/chi-tiet/doc--{job_id}",
        source_url_hash=f"hash-{job_id}",
        document_id=document_id or job_id,
        status=status,
        attempts=attempts,
        updated_at=updated_at,
    )


def test_claim_next_job_ignores_skipped_and_exhausted_failed_by_default() -> None:
    session_factory = _session_factory()
    now = _now()
    with session_factory.begin() as session:
        session.add_all(
            [
                _job(job_id=1, status=CrawlStatus.SKIPPED, attempts=1, updated_at=now),
                _job(job_id=2, status=CrawlStatus.FAILED, attempts=3, updated_at=now + timedelta(seconds=1)),
                _job(job_id=3, status=CrawlStatus.DISCOVERED, attempts=0, updated_at=now + timedelta(seconds=2)),
            ]
        )

    with session_factory.begin() as session:
        claimed = _claim_next_job(session, max_attempts=3)

    assert claimed == (3, 3, "https://vbpl.vn/van-ban/chi-tiet/doc--3")


def test_claim_next_job_can_retry_skipped_jobs() -> None:
    session_factory = _session_factory()
    now = _now()
    with session_factory.begin() as session:
        session.add(_job(job_id=1, status=CrawlStatus.SKIPPED, attempts=1, updated_at=now))

    with session_factory.begin() as session:
        claimed = _claim_next_job(session, max_attempts=3, retry_skipped=True)

    assert claimed == (1, 1, "https://vbpl.vn/van-ban/chi-tiet/doc--1")


def test_claim_next_job_can_retry_exhausted_failed_jobs() -> None:
    session_factory = _session_factory()
    now = _now()
    with session_factory.begin() as session:
        session.add(_job(job_id=1, status=CrawlStatus.FAILED, attempts=3, updated_at=now))

    with session_factory.begin() as session:
        claimed = _claim_next_job(session, max_attempts=3, retry_exhausted=True)

    assert claimed == (1, 1, "https://vbpl.vn/van-ban/chi-tiet/doc--1")
