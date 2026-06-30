from __future__ import annotations

import hashlib

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from law_crawler.models import (
    CrawlJob,
    CrawlStatus,
    DuplicateLegalIdentityReview,
    LegalDocument,
    LegalDocumentAnchor,
    LegalDocumentAnnex,
    LegalDocumentArticle,
    LegalDocumentClause,
    LegalDocumentContent,
    LegalDocumentForm,
    LegalDocumentPoint,
    PdfReviewDocument,
    LegalDocumentRelationship,
    LegalDocumentTable,
    LegalDocumentVersion,
    RelationshipType,
)
from law_crawler.parser import ParsedDocument
from bs4 import BeautifulSoup


def persist_parsed_document(
    session: Session,
    *,
    document_id: int,
    source_url: str,
    parsed: ParsedDocument,
    title: str | None = None,
    document_number: str | None = None,
    document_type: str | None = None,
    issued_date=None,
    effective_date=None,
    expired_date=None,
    validity_status: str | None = None,
    issuing_authority: str | None = None,
    relationships=(),
) -> LegalDocumentVersion:
    title = title or parsed.title or f"VBPL document {document_id}"
    document = session.get(LegalDocument, document_id)
    if document is None:
        document = LegalDocument(id=document_id, title=title, source=source_url)
        session.add(document)
    else:
        document.title = title
        document.source = source_url
    document.document_number = document_number
    document.document_type = document_type
    document.issued_date = issued_date
    document.effective_date = effective_date
    document.expired_date = expired_date
    document.validity_status = validity_status
    document.issuing_authority = issuing_authority
    _flag_duplicate_legal_identity(
        session,
        document=document,
        document_number=document_number,
        issued_date=issued_date,
        issuing_authority=issuing_authority,
        source_url=source_url,
    )

    version_label = parsed.source_hash[:12]
    version = session.scalar(
        select(LegalDocumentVersion).where(
            LegalDocumentVersion.document_id == document_id,
            LegalDocumentVersion.version_label == version_label,
        )
    )
    if version is None:
        session.execute(
            update(LegalDocumentVersion)
            .where(LegalDocumentVersion.document_id == document_id)
            .values(is_current=False)
        )
        version = LegalDocumentVersion(
            document_id=document_id,
            version_label=version_label,
            source_url=source_url,
            is_current=True,
            source_hash=parsed.source_hash,
            effective_date=effective_date,
            expired_date=expired_date,
            validity_status=validity_status,
        )
        session.add(version)
        session.flush()
    else:
        version.is_current = True
        version.source_url = source_url
        version.effective_date = effective_date
        version.expired_date = expired_date
        version.validity_status = validity_status
        session.execute(
            update(LegalDocumentVersion)
            .where(
                LegalDocumentVersion.document_id == document_id,
                LegalDocumentVersion.id != version.id,
            )
            .values(is_current=False, superseded_by_version_id=version.id)
        )

    document.current_version_id = version.id

    _replace_content(session, document_id=document_id, version_id=version.id, parsed=parsed)
    _replace_structured_content(session, document_id=document_id, version_id=version.id, parsed=parsed)
    replace_relationships(session, document_id=document_id, relationships=relationships)
    return version


def persist_pdf_review_document(
    session: Session,
    *,
    document_id: int,
    source_url: str,
    html: str,
    pdf_file_name: str | None,
    title: str | None = None,
    document_number: str | None = None,
    document_type: str | None = None,
    issued_date=None,
    effective_date=None,
    expired_date=None,
    validity_status: str | None = None,
    issuing_authority: str | None = None,
    review_reason: str = "PDF_TEXT_REQUIRES_MANUAL_REVIEW",
    delete_normal_document_data: bool = True,
) -> PdfReviewDocument:
    if delete_normal_document_data:
        _delete_normal_document_data(session, document_id=document_id)
    extracted_text = BeautifulSoup(html, "html.parser").get_text("\n").strip()
    review_document = session.get(PdfReviewDocument, document_id)
    if review_document is None:
        review_document = PdfReviewDocument(document_id=document_id)
        session.add(review_document)
    review_document.source_url = source_url
    review_document.title = title
    review_document.document_number = document_number
    review_document.document_type = document_type
    review_document.issued_date = issued_date
    review_document.effective_date = effective_date
    review_document.expired_date = expired_date
    review_document.validity_status = validity_status
    review_document.issuing_authority = issuing_authority
    review_document.pdf_file_name = pdf_file_name
    review_document.extracted_text = extracted_text
    review_document.extracted_html = html
    review_document.review_reason = review_reason
    return review_document


def replace_relationships(session: Session, *, document_id: int, relationships) -> None:
    if relationships is None:
        return
    session.execute(delete(LegalDocumentRelationship).where(LegalDocumentRelationship.document_id == document_id))
    seen: set[tuple[int, RelationshipType]] = set()
    for relationship in relationships:
        try:
            related_document_id = int(relationship.related_document_id)
            relationship_type = RelationshipType(relationship.relationship_type)
        except (AttributeError, TypeError, ValueError):
            continue
        if related_document_id == document_id:
            continue
        key = (related_document_id, relationship_type)
        if key in seen:
            continue
        seen.add(key)
        session.add(
            LegalDocumentRelationship(
                document_id=document_id,
                related_document_id=related_document_id,
                relationship_type=relationship_type,
                source_text=relationship.source_text,
            )
        )


def _flag_duplicate_legal_identity(
    session: Session,
    *,
    document: LegalDocument,
    document_number: str | None,
    issued_date,
    issuing_authority: str | None,
    source_url: str,
) -> None:
    identity_key = _legal_identity_key(document_number, issued_date, issuing_authority)
    if identity_key is None:
        return

    candidates = session.scalars(
        select(LegalDocument).where(
            LegalDocument.id != document.id,
            LegalDocument.document_number.is_not(None),
            LegalDocument.issued_date == issued_date,
            LegalDocument.issuing_authority.is_not(None),
        )
    )
    for candidate in candidates:
        if _legal_identity_key(candidate.document_number, candidate.issued_date, candidate.issuing_authority) != identity_key:
            continue
        first_id, second_id = sorted((int(document.id), int(candidate.id)))
        existing = session.scalar(
            select(DuplicateLegalIdentityReview).where(
                DuplicateLegalIdentityReview.document_id == first_id,
                DuplicateLegalIdentityReview.duplicate_document_id == second_id,
            )
        )
        if existing is not None:
            existing.identity_key = identity_key
            existing.document_number = document_number
            existing.issued_date = issued_date
            existing.issuing_authority = issuing_authority
            existing.source_url = source_url if first_id == document.id else candidate.source
            existing.duplicate_source_url = candidate.source if first_id == document.id else source_url
            if existing.status == "RESOLVED":
                existing.status = "OPEN"
            continue
        session.add(
            DuplicateLegalIdentityReview(
                document_id=first_id,
                duplicate_document_id=second_id,
                identity_key=identity_key,
                document_number=document_number,
                issued_date=issued_date,
                issuing_authority=issuing_authority,
                source_url=source_url if first_id == document.id else candidate.source,
                duplicate_source_url=candidate.source if first_id == document.id else source_url,
                status="OPEN",
                review_reason="SAME_LEGAL_IDENTITY_DIFFERENT_DOCUMENT_ID",
            )
        )


def _legal_identity_key(document_number: str | None, issued_date, issuing_authority: str | None) -> str | None:
    normalized_number = _normalize_identity_text(document_number)
    normalized_authority = _normalize_identity_text(issuing_authority)
    if not normalized_number or issued_date is None or not normalized_authority:
        return None
    raw_key = f"{normalized_number}|{issued_date.isoformat()}|{normalized_authority}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _normalize_identity_text(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _delete_normal_document_data(session: Session, *, document_id: int) -> None:
    version_ids = select(LegalDocumentVersion.id).where(LegalDocumentVersion.document_id == document_id)
    article_ids = select(LegalDocumentArticle.id).where(LegalDocumentArticle.version_id.in_(version_ids))
    clause_ids = select(LegalDocumentClause.id).where(LegalDocumentClause.article_id.in_(article_ids))
    session.execute(delete(LegalDocumentAnchor).where(LegalDocumentAnchor.version_id.in_(version_ids)))
    session.execute(delete(LegalDocumentTable).where(LegalDocumentTable.version_id.in_(version_ids)))
    session.execute(delete(LegalDocumentForm).where(LegalDocumentForm.version_id.in_(version_ids)))
    session.execute(delete(LegalDocumentAnnex).where(LegalDocumentAnnex.version_id.in_(version_ids)))
    session.execute(delete(LegalDocumentPoint).where(LegalDocumentPoint.clause_id.in_(clause_ids)))
    session.execute(delete(LegalDocumentClause).where(LegalDocumentClause.article_id.in_(article_ids)))
    session.execute(delete(LegalDocumentArticle).where(LegalDocumentArticle.version_id.in_(version_ids)))
    session.execute(delete(LegalDocumentContent).where(LegalDocumentContent.document_id == document_id))
    session.execute(delete(LegalDocumentRelationship).where(LegalDocumentRelationship.document_id == document_id))
    document = session.get(LegalDocument, document_id)
    if document is not None:
        document.current_version_id = None
        session.flush()
    session.execute(delete(LegalDocumentVersion).where(LegalDocumentVersion.document_id == document_id))
    session.execute(delete(LegalDocument).where(LegalDocument.id == document_id))


def upsert_crawl_job(session: Session, *, source_url: str, document_id: int | None) -> CrawlJob:
    source_url_hash = hashlib.sha256(source_url.encode("utf-8")).hexdigest()
    job = session.scalar(select(CrawlJob).where(CrawlJob.source_url_hash == source_url_hash))
    if job is None:
        job = CrawlJob(
            source_url=source_url,
            source_url_hash=source_url_hash,
            document_id=document_id,
            status=CrawlStatus.DISCOVERED,
        )
        session.add(job)
    elif document_id is not None:
        job.document_id = document_id
    return job


def _replace_content(session: Session, *, document_id: int, version_id: int, parsed: ParsedDocument) -> None:
    content = session.get(LegalDocumentContent, document_id)
    if content is None:
        content = LegalDocumentContent(document_id=document_id, version_id=version_id, content_html=parsed.content_html)
        session.add(content)
    content.version_id = version_id
    content.content_html = parsed.content_html
    content.content_text = parsed.content_text


def _replace_structured_content(
    session: Session,
    *,
    document_id: int,
    version_id: int,
    parsed: ParsedDocument,
) -> None:
    article_ids = select(LegalDocumentArticle.id).where(LegalDocumentArticle.version_id == version_id)
    session.execute(delete(LegalDocumentAnchor).where(LegalDocumentAnchor.version_id == version_id))
    session.execute(delete(LegalDocumentTable).where(LegalDocumentTable.version_id == version_id))
    session.execute(delete(LegalDocumentForm).where(LegalDocumentForm.version_id == version_id))
    session.execute(delete(LegalDocumentAnnex).where(LegalDocumentAnnex.version_id == version_id))
    session.execute(delete(LegalDocumentPoint).where(LegalDocumentPoint.clause_id.in_(select(LegalDocumentClause.id).where(LegalDocumentClause.article_id.in_(article_ids)))))
    session.execute(delete(LegalDocumentClause).where(LegalDocumentClause.article_id.in_(article_ids)))
    session.execute(delete(LegalDocumentArticle).where(LegalDocumentArticle.version_id == version_id))
    session.flush()

    article_by_anchor: dict[str, LegalDocumentArticle] = {}
    for parsed_article in parsed.articles:
        article = LegalDocumentArticle(
            document_id=document_id,
            version_id=version_id,
            article_number=parsed_article.number,
            article_occurrence=parsed_article.occurrence_index,
            title=parsed_article.title,
            stable_anchor=parsed_article.stable_anchor,
            order_index=parsed_article.order_index,
            content_text=parsed_article.content_text,
            content_html=parsed_article.content_html,
        )
        session.add(article)
        session.flush()
        article_by_anchor[parsed_article.stable_anchor] = article
        _add_anchor(session, version_id, parsed_article.stable_anchor, "ARTICLE", "legal_document_articles", article.id)

        for parsed_clause in parsed_article.clauses:
            clause = LegalDocumentClause(
                article_id=article.id,
                clause_number=parsed_clause.number,
                clause_occurrence=parsed_clause.occurrence_index,
                stable_anchor=parsed_clause.stable_anchor,
                order_index=parsed_clause.order_index,
                content_text=parsed_clause.content_text,
                content_html=parsed_clause.content_html,
            )
            session.add(clause)
            session.flush()
            _add_anchor(session, version_id, parsed_clause.stable_anchor, "CLAUSE", "legal_document_clauses", clause.id)

            for parsed_point in parsed_clause.points:
                point = LegalDocumentPoint(
                    clause_id=clause.id,
                    point_label=parsed_point.label,
                    point_occurrence=parsed_point.occurrence_index,
                    stable_anchor=parsed_point.stable_anchor,
                    order_index=parsed_point.order_index,
                    content_text=parsed_point.content_text,
                    content_html=parsed_point.content_html,
                )
                session.add(point)
                session.flush()
                _add_anchor(session, version_id, parsed_point.stable_anchor, "POINT", "legal_document_points", point.id)

    for parsed_table in parsed.tables:
        article = article_by_anchor.get(parsed_table.article_anchor or "")
        table = LegalDocumentTable(
            version_id=version_id,
            article_id=article.id if article else None,
            stable_anchor=parsed_table.stable_anchor,
            order_index=parsed_table.order_index,
            caption=parsed_table.caption,
            html=parsed_table.html,
            text=parsed_table.text,
        )
        session.add(table)
        session.flush()
        _add_anchor(session, version_id, parsed_table.stable_anchor, "TABLE", "legal_document_tables", table.id)

    for parsed_form in parsed.forms:
        form = LegalDocumentForm(
            version_id=version_id,
            stable_anchor=parsed_form.stable_anchor,
            title=parsed_form.title,
            source_url=parsed_form.source_url,
            html=parsed_form.html,
            text=parsed_form.text,
        )
        session.add(form)
        session.flush()
        _add_anchor(session, version_id, parsed_form.stable_anchor, "FORM", "legal_document_forms", form.id)

    for parsed_annex in parsed.annexes:
        annex = LegalDocumentAnnex(
            version_id=version_id,
            stable_anchor=parsed_annex.stable_anchor,
            title=parsed_annex.title,
            order_index=parsed_annex.order_index,
            html=parsed_annex.html,
            text=parsed_annex.text,
        )
        session.add(annex)
        session.flush()
        _add_anchor(session, version_id, parsed_annex.stable_anchor, "ANNEX", "legal_document_annexes", annex.id)


def _add_anchor(
    session: Session,
    version_id: int,
    stable_anchor: str,
    anchor_type: str,
    target_table: str,
    target_id: int,
) -> None:
    session.add(
        LegalDocumentAnchor(
            version_id=version_id,
            stable_anchor=stable_anchor,
            anchor_type=anchor_type,
            target_table=target_table,
            target_id=target_id,
        )
    )
