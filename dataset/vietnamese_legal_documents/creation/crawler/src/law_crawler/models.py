from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


BIG_INT = BigInteger().with_variant(Integer(), "sqlite")
MEDIUM_TEXT = MEDIUMTEXT().with_variant(Text(), "sqlite")
LONG_TEXT = LONGTEXT().with_variant(Text(), "sqlite")


class Base(DeclarativeBase):
    pass


class RelationshipType(str, enum.Enum):
    AMENDS = "AMENDS"
    REPLACES = "REPLACES"
    GUIDES = "GUIDES"
    IMPLEMENTS = "IMPLEMENTS"
    REFERENCES = "REFERENCES"
    EXPIRES = "EXPIRES"
    CONSOLIDATES = "CONSOLIDATES"
    CORRECTS = "CORRECTS"
    OTHER = "OTHER"


class CrawlStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    CRAWLED = "CRAWLED"
    PDF_REVIEW = "PDF_REVIEW"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(1500), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(255))
    issued_date: Mapped[date | None] = mapped_column(Date)
    document_type: Mapped[str | None] = mapped_column(String(255))
    effective_date: Mapped[date | None] = mapped_column(Date)
    expired_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str | None] = mapped_column(String(1500))
    validity_status: Mapped[str | None] = mapped_column(String(255))
    issuing_authority: Mapped[str | None] = mapped_column(String(500))
    current_version_id: Mapped[int | None] = mapped_column(
        BIG_INT,
        ForeignKey("legal_document_versions.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    versions: Mapped[list["LegalDocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="LegalDocumentVersion.document_id",
    )
    current_version: Mapped["LegalDocumentVersion | None"] = relationship(
        foreign_keys=[current_version_id],
        post_update=True,
    )


class LegalDocumentVersion(Base):
    __tablename__ = "legal_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_label", name="uk_document_version_label"),
        Index("idx_document_versions_current", "document_id", "is_current"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("legal_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_label: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1500))
    effective_date: Mapped[date | None] = mapped_column(Date)
    expired_date: Mapped[date | None] = mapped_column(Date)
    validity_status: Mapped[str | None] = mapped_column(String(255))
    superseded_by_version_id: Mapped[int | None] = mapped_column(
        BIG_INT,
        ForeignKey("legal_document_versions.id", ondelete="SET NULL"),
    )
    amendment_summary: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    source_hash: Mapped[str | None] = mapped_column(String(64))

    document: Mapped[LegalDocument] = relationship(
        back_populates="versions",
        foreign_keys=[document_id],
    )


class LegalDocumentContent(Base):
    __tablename__ = "legal_document_contents"

    document_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("legal_documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    version_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("legal_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    content_html: Mapped[str] = mapped_column(MEDIUM_TEXT, nullable=False)
    content_text: Mapped[str | None] = mapped_column(MEDIUM_TEXT)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class LegalDocumentArticle(Base):
    __tablename__ = "legal_document_articles"
    __table_args__ = (
        UniqueConstraint("version_id", "article_number", "article_occurrence", name="uk_version_article_occurrence"),
        Index("idx_articles_anchor", "stable_anchor"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    version_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("legal_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    article_number: Mapped[str] = mapped_column(String(64), nullable=False)
    article_occurrence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str | None] = mapped_column(String(1000))
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(MEDIUM_TEXT, nullable=False)
    content_html: Mapped[str | None] = mapped_column(MEDIUM_TEXT)

    clauses: Mapped[list["LegalDocumentClause"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )


class LegalDocumentClause(Base):
    __tablename__ = "legal_document_clauses"
    __table_args__ = (
        UniqueConstraint("article_id", "clause_number", "clause_occurrence", name="uk_article_clause_occurrence"),
        Index("idx_clauses_anchor", "stable_anchor"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("legal_document_articles.id", ondelete="CASCADE"),
        nullable=False,
    )
    clause_number: Mapped[str] = mapped_column(String(64), nullable=False)
    clause_occurrence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(MEDIUM_TEXT, nullable=False)
    content_html: Mapped[str | None] = mapped_column(MEDIUM_TEXT)

    article: Mapped[LegalDocumentArticle] = relationship(back_populates="clauses")
    points: Mapped[list["LegalDocumentPoint"]] = relationship(
        back_populates="clause",
        cascade="all, delete-orphan",
    )


class LegalDocumentPoint(Base):
    __tablename__ = "legal_document_points"
    __table_args__ = (
        UniqueConstraint("clause_id", "point_label", "point_occurrence", name="uk_clause_point_occurrence"),
        Index("idx_points_anchor", "stable_anchor"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    clause_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("legal_document_clauses.id", ondelete="CASCADE"),
        nullable=False,
    )
    point_label: Mapped[str] = mapped_column(String(32), nullable=False)
    point_occurrence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content_text: Mapped[str] = mapped_column(MEDIUM_TEXT, nullable=False)
    content_html: Mapped[str | None] = mapped_column(MEDIUM_TEXT)

    clause: Mapped[LegalDocumentClause] = relationship(back_populates="points")


class LegalDocumentTable(Base):
    __tablename__ = "legal_document_tables"

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(BIG_INT, ForeignKey("legal_document_versions.id", ondelete="CASCADE"))
    article_id: Mapped[int | None] = mapped_column(BIG_INT, ForeignKey("legal_document_articles.id", ondelete="SET NULL"))
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    caption: Mapped[str | None] = mapped_column(String(1000))
    html: Mapped[str] = mapped_column(MEDIUM_TEXT, nullable=False)
    text: Mapped[str | None] = mapped_column(MEDIUM_TEXT)


class LegalDocumentForm(Base):
    __tablename__ = "legal_document_forms"

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(BIG_INT, ForeignKey("legal_document_versions.id", ondelete="CASCADE"))
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    html: Mapped[str | None] = mapped_column(MEDIUM_TEXT)
    text: Mapped[str | None] = mapped_column(MEDIUM_TEXT)


class LegalDocumentAnnex(Base):
    __tablename__ = "legal_document_annexes"

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(BIG_INT, ForeignKey("legal_document_versions.id", ondelete="CASCADE"))
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000))
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    html: Mapped[str | None] = mapped_column(LONG_TEXT)
    text: Mapped[str | None] = mapped_column(LONG_TEXT)


class LegalDocumentAnchor(Base):
    __tablename__ = "legal_document_anchors"
    __table_args__ = (UniqueConstraint("version_id", "stable_anchor", name="uk_version_stable_anchor"),)

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(BIG_INT, ForeignKey("legal_document_versions.id", ondelete="CASCADE"))
    stable_anchor: Mapped[str] = mapped_column(String(255), nullable=False)
    anchor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_table: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int | None] = mapped_column(BIG_INT)


class LegalDocumentRelationship(Base):
    __tablename__ = "legal_document_relationships"
    __table_args__ = (
        UniqueConstraint("document_id", "related_document_id", "relationship_type", name="uk_legal_doc_relationship"),
        Index("idx_relationship_type", "relationship_type"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    related_document_id: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    relationship_type: Mapped[RelationshipType] = mapped_column(
        Enum(RelationshipType, native_enum=False, length=32),
        nullable=False,
    )
    source_text: Mapped[str | None] = mapped_column(String(1000))


class DuplicateLegalIdentityReview(Base):
    __tablename__ = "duplicate_legal_identity_reviews"
    __table_args__ = (
        UniqueConstraint("document_id", "duplicate_document_id", name="uk_duplicate_legal_identity_pair"),
        Index("idx_duplicate_legal_identity_status", "status"),
        Index("idx_duplicate_legal_identity_key", "identity_key"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    duplicate_document_id: Mapped[int] = mapped_column(BIG_INT, nullable=False)
    identity_key: Mapped[str] = mapped_column(String(64), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(255))
    issued_date: Mapped[date | None] = mapped_column(Date)
    issuing_authority: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(1500))
    duplicate_source_url: Mapped[str | None] = mapped_column(String(1500))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    review_reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="SAME_LEGAL_IDENTITY_DIFFERENT_DOCUMENT_ID",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    __table_args__ = (
        UniqueConstraint("source_url_hash", name="uk_crawl_jobs_source_url_hash"),
        Index("idx_crawl_jobs_status", "status"),
        Index("idx_crawl_jobs_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    source_url: Mapped[str] = mapped_column(String(1500), nullable=False)
    source_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[int | None] = mapped_column(BIG_INT)
    status: Mapped[CrawlStatus] = mapped_column(
        Enum(CrawlStatus, native_enum=False, length=32),
        nullable=False,
        default=CrawlStatus.DISCOVERED,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    discovered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PdfReviewDocument(Base):
    __tablename__ = "pdf_review_documents"

    document_id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=False)
    source_url: Mapped[str | None] = mapped_column(String(1500))
    title: Mapped[str | None] = mapped_column(String(1500))
    document_number: Mapped[str | None] = mapped_column(String(255))
    document_type: Mapped[str | None] = mapped_column(String(255))
    issuing_authority: Mapped[str | None] = mapped_column(String(500))
    issued_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expired_date: Mapped[date | None] = mapped_column(Date)
    validity_status: Mapped[str | None] = mapped_column(String(255))
    pdf_file_name: Mapped[str | None] = mapped_column(String(1000))
    extracted_text: Mapped[str | None] = mapped_column(LONG_TEXT)
    extracted_html: Mapped[str | None] = mapped_column(LONG_TEXT)
    review_reason: Mapped[str] = mapped_column(String(255), nullable=False, default="PDF_TEXT_REQUIRES_MANUAL_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
