from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
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


class LegalDocument(Base):
    __tablename__ = "legal_documents"

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(1500), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(255))
    document_type: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(1500))


class GovernmentQnaItem(Base):
    __tablename__ = "government_qna_items"
    __table_args__ = (
        UniqueConstraint("source_url_hash", name="uk_government_qna_source_url_hash"),
        Index("idx_government_qna_source", "source_name"),
        Index("idx_government_qna_published_at", "published_date"),
        Index("idx_government_qna_item_citation_status", "citation_status"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    external_id: Mapped[int | None] = mapped_column(BIG_INT)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1500), nullable=False)
    source_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    detail_url: Mapped[str | None] = mapped_column(String(1500))
    original_url: Mapped[str | None] = mapped_column(String(1500))
    title: Mapped[str] = mapped_column(String(1500), nullable=False)
    question_text: Mapped[str | None] = mapped_column(MEDIUM_TEXT)
    answer_text: Mapped[str | None] = mapped_column(LONG_TEXT)
    answer_html: Mapped[str | None] = mapped_column(LONG_TEXT)
    summary_text: Mapped[str | None] = mapped_column(MEDIUM_TEXT)
    responding_authority: Mapped[str | None] = mapped_column(String(500))
    category_name: Mapped[str | None] = mapped_column(String(500))
    tags: Mapped[str | None] = mapped_column(String(1000))
    published_date: Mapped[date | None] = mapped_column(Date)
    source_payload_json: Mapped[str | None] = mapped_column(LONG_TEXT)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    citation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNRESOLVED")
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    crawled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    citations: Mapped[list["GovernmentQnaCitation"]] = relationship(
        back_populates="qna_item",
        cascade="all, delete-orphan",
    )


class GovernmentQnaCitation(Base):
    __tablename__ = "government_qna_citations"
    __table_args__ = (
        UniqueConstraint("qna_item_id", "citation_hash", name="uk_government_qna_citation_hash"),
        Index("idx_government_qna_citation_document", "matched_document_id"),
        Index("idx_government_qna_citation_status", "match_status"),
        Index("idx_government_qna_citation_number", "document_number"),
    )

    id: Mapped[int] = mapped_column(BIG_INT, primary_key=True, autoincrement=True)
    qna_item_id: Mapped[int] = mapped_column(
        BIG_INT,
        ForeignKey("government_qna_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    citation_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str] = mapped_column(String(1500), nullable=False)
    document_number: Mapped[str | None] = mapped_column(String(255))
    document_title: Mapped[str | None] = mapped_column(String(1000))
    article_refs: Mapped[str | None] = mapped_column(String(1000))
    clause_refs: Mapped[str | None] = mapped_column(String(1000))
    point_refs: Mapped[str | None] = mapped_column(String(1000))
    matched_document_id: Mapped[int | None] = mapped_column(BIG_INT)
    matched_document_title: Mapped[str | None] = mapped_column(String(1500))
    matched_document_number: Mapped[str | None] = mapped_column(String(255))
    matched_document_source: Mapped[str | None] = mapped_column(String(2048))
    match_status: Mapped[str] = mapped_column(String(32), nullable=False)
    match_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    qna_item: Mapped[GovernmentQnaItem] = relationship(back_populates="citations")
