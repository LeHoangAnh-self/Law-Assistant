from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class RequeueQualitySummary:
    empty_content_docs: int
    no_article_docs: int
    long_title_docs: int
    requeued_jobs: int
    dry_run: bool


def requeue_quality_issues(
    engine: Engine,
    *,
    execute: bool,
    empty_content_max_chars: int = 0,
    no_article_min_chars: int = 500,
    long_title_min_chars: int = 1000,
) -> RequeueQualitySummary:
    params = {
        "empty_content_max_chars": empty_content_max_chars,
        "no_article_min_chars": no_article_min_chars,
        "long_title_min_chars": long_title_min_chars,
        "reason": (
            "REQUEUED_QUALITY_AUDIT: parser/fetcher improved; "
            "previous crawl had empty content, no parsed top-level units, or long article titles"
        ),
    }
    with engine.begin() as connection:
        empty_content_docs = connection.scalar(_empty_content_count_query(), params) or 0
        no_article_docs = connection.scalar(_no_article_count_query(), params) or 0
        long_title_docs = connection.scalar(_long_title_count_query(), params) or 0
        requeued_jobs = 0
        if execute:
            result = connection.execute(_requeue_jobs_query(), params)
            requeued_jobs = result.rowcount or 0

    return RequeueQualitySummary(
        empty_content_docs=empty_content_docs,
        no_article_docs=no_article_docs,
        long_title_docs=long_title_docs,
        requeued_jobs=requeued_jobs,
        dry_run=not execute,
    )


def _quality_issue_docs_query() -> str:
    return """
        select d.id as document_id
        from legal_documents d
        join legal_document_contents lc
          on lc.document_id = d.id
         and lc.version_id = d.current_version_id
        where length(coalesce(lc.content_text, '')) <= :empty_content_max_chars

        union distinct

        select d.id as document_id
        from legal_documents d
        join legal_document_contents lc
          on lc.document_id = d.id
         and lc.version_id = d.current_version_id
        where length(coalesce(lc.content_text, '')) >= :no_article_min_chars
          and not exists (
              select 1
              from legal_document_articles a
              where a.version_id = d.current_version_id
              limit 1
          )

        union distinct

        select distinct a.document_id
        from legal_document_articles a
        where length(coalesce(a.title, '')) >= :long_title_min_chars
    """


def _empty_content_count_query():
    return text(
        """
        select count(*)
        from legal_documents d
        join legal_document_contents lc
          on lc.document_id = d.id
         and lc.version_id = d.current_version_id
        where length(coalesce(lc.content_text, '')) <= :empty_content_max_chars
        """
    )


def _no_article_count_query():
    return text(
        """
        select count(*)
        from legal_documents d
        join legal_document_contents lc
          on lc.document_id = d.id
         and lc.version_id = d.current_version_id
        where length(coalesce(lc.content_text, '')) >= :no_article_min_chars
          and not exists (
              select 1
              from legal_document_articles a
              where a.version_id = d.current_version_id
              limit 1
          )
        """
    )


def _long_title_count_query():
    return text(
        """
        select count(distinct document_id)
        from legal_document_articles
        where length(coalesce(title, '')) >= :long_title_min_chars
        """
    )


def _requeue_jobs_query():
    return text(
        f"""
        update crawl_jobs j
        join (
            {_quality_issue_docs_query()}
        ) q on q.document_id = j.document_id
        set
            j.status = 'DISCOVERED',
            j.attempts = 0,
            j.last_error = :reason,
            j.crawled_at = null
        where j.status in ('CRAWLED', 'FAILED', 'SKIPPED')
        """
    )
