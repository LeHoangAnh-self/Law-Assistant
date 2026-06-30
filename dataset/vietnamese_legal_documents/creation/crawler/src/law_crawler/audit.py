from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine, text


VBPL_API_400_PATTERN = "%400 Client Error: Bad Request%qtdc/public/doc/%"


@dataclass(frozen=True)
class FailedJobAuditRow:
    job_id: int
    document_id: int | None
    status: str
    attempts: int
    source_url: str
    last_error: str | None
    updated_at: datetime | None


@dataclass(frozen=True)
class FailedJobAuditSummary:
    total_matches: int
    rows: list[FailedJobAuditRow]
    requeued_jobs: int = 0
    dry_run: bool = True


def audit_vbpl_api_400_failures(
    engine: Engine,
    *,
    limit: int = 100,
    requeue: bool = False,
    execute: bool = False,
) -> FailedJobAuditSummary:
    with engine.begin() as connection:
        total = connection.scalar(
            text(
                """
                select count(*)
                from crawl_jobs
                where last_error like :pattern
                """
            ),
            {"pattern": VBPL_API_400_PATTERN},
        )
        rows = connection.execute(
            text(
                """
                select id, document_id, status, attempts, source_url, last_error, updated_at
                from crawl_jobs
                where last_error like :pattern
                order by updated_at desc, id desc
                limit :limit
                """
            ),
            {"pattern": VBPL_API_400_PATTERN, "limit": limit},
        ).mappings()
        row_list = list(rows)
        requeued = 0
        if requeue and execute:
            result = connection.execute(
                text(
                    """
                    update crawl_jobs
                    set status = 'DISCOVERED',
                        attempts = 0,
                        last_error = 'REQUEUED_VBPL_API_400: fallback fetcher improved',
                        crawled_at = null
                    where last_error like :pattern
                    """
                ),
                {"pattern": VBPL_API_400_PATTERN},
            )
            requeued = int(result.rowcount or 0)

    return FailedJobAuditSummary(
        total_matches=int(total or 0),
        rows=[
            FailedJobAuditRow(
                job_id=int(row["id"]),
                document_id=int(row["document_id"]) if row["document_id"] is not None else None,
                status=str(row["status"]),
                attempts=int(row["attempts"]),
                source_url=str(row["source_url"]),
                last_error=str(row["last_error"])[:500] if row["last_error"] is not None else None,
                updated_at=row["updated_at"],
            )
            for row in row_list
        ],
        requeued_jobs=requeued,
        dry_run=not (requeue and execute),
    )
