from sqlalchemy import create_engine, text

from law_crawler.audit import audit_vbpl_api_400_failures


def build_test_engine():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                create table crawl_jobs (
                    id integer primary key,
                    document_id integer,
                    status varchar(32),
                    attempts integer,
                    source_url varchar(1500),
                    last_error text,
                    crawled_at datetime,
                    updated_at datetime
                )
                """
            )
        )
        connection.execute(
            text(
                """
                insert into crawl_jobs
                    (id, document_id, status, attempts, source_url, last_error, crawled_at, updated_at)
                values
                    (1, 155366, 'FAILED', 3, 'https://vbpl.vn/doc--155366',
                     '400 Client Error: Bad Request for url: https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/155366',
                     null,
                     '2026-06-22 19:31:08'),
                    (2, 160483, 'CRAWLED', 4, 'https://vbpl.vn/doc--160483',
                     null,
                     '2026-06-22 19:32:08',
                     '2026-06-22 19:32:08')
                """
            )
        )
    return engine


def test_audit_vbpl_api_400_failures_lists_matching_jobs() -> None:
    engine = build_test_engine()

    summary = audit_vbpl_api_400_failures(engine)

    assert summary.total_matches == 1
    assert summary.requeued_jobs == 0
    assert summary.dry_run
    assert len(summary.rows) == 1
    assert summary.rows[0].document_id == 155366
    assert summary.rows[0].status == "FAILED"


def test_audit_vbpl_api_400_failures_requeues_only_when_executed() -> None:
    engine = build_test_engine()

    dry_run = audit_vbpl_api_400_failures(engine, requeue=True, execute=False)
    assert dry_run.requeued_jobs == 0
    with engine.connect() as connection:
        status = connection.scalar(text("select status from crawl_jobs where id = 1"))
    assert status == "FAILED"

    executed = audit_vbpl_api_400_failures(engine, requeue=True, execute=True)

    assert executed.requeued_jobs == 1
    assert not executed.dry_run
    with engine.connect() as connection:
        row = connection.execute(
            text("select status, attempts, last_error from crawl_jobs where id = 1")
        ).mappings().one()
        unchanged = connection.scalar(text("select status from crawl_jobs where id = 2"))
    assert row["status"] == "DISCOVERED"
    assert row["attempts"] == 0
    assert row["last_error"] == "REQUEUED_VBPL_API_400: fallback fetcher improved"
    assert unchanged == "CRAWLED"
