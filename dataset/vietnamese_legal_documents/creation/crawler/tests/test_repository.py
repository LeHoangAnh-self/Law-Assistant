from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from law_crawler.models import Base, DuplicateLegalIdentityReview, LegalDocument
from law_crawler.parser import parse_document_html
from law_crawler.repository import persist_parsed_document


def test_same_legal_identity_different_document_ids_are_flagged_not_merged() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    parsed = parse_document_html(
        """
        <div id="toanvancontent">
          <p>QUYẾT ĐỊNH</p>
          <p>Điều 1. Phạm vi điều chỉnh</p>
          <p>1. Nội dung.</p>
        </div>
        """
    )

    with session_factory.begin() as session:
        persist_parsed_document(
            session,
            document_id=100,
            source_url="https://vbpl.vn/doc--100",
            parsed=parsed,
            title="Quyết định 01",
            document_number="01/2026/QĐ-UBND",
            issued_date=date(2026, 1, 1),
            issuing_authority="Ủy ban nhân dân tỉnh A",
        )
        persist_parsed_document(
            session,
            document_id=200,
            source_url="https://vbpl.vn/doc--200",
            parsed=parsed,
            title="Quyết định 01 bản khác",
            document_number=" 01/2026/QĐ-UBND ",
            issued_date=date(2026, 1, 1),
            issuing_authority="ủy ban nhân dân tỉnh A",
        )

    with session_factory.begin() as session:
        documents = session.scalars(select(LegalDocument).order_by(LegalDocument.id)).all()
        reviews = session.scalars(select(DuplicateLegalIdentityReview)).all()

    assert [document.id for document in documents] == [100, 200]
    assert len(reviews) == 1
    assert reviews[0].document_id == 100
    assert reviews[0].duplicate_document_id == 200
    assert reviews[0].status == "OPEN"
    assert reviews[0].review_reason == "SAME_LEGAL_IDENTITY_DIFFERENT_DOCUMENT_ID"


def test_duplicate_identity_review_requires_complete_identity() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    parsed = parse_document_html("<div id='toanvancontent'><p>Điều 1. Nội dung</p></div>")

    with session_factory.begin() as session:
        persist_parsed_document(
            session,
            document_id=100,
            source_url="https://vbpl.vn/doc--100",
            parsed=parsed,
            document_number="01/2026/QĐ-UBND",
            issued_date=date(2026, 1, 1),
            issuing_authority=None,
        )
        persist_parsed_document(
            session,
            document_id=200,
            source_url="https://vbpl.vn/doc--200",
            parsed=parsed,
            document_number="01/2026/QĐ-UBND",
            issued_date=date(2026, 1, 1),
            issuing_authority=None,
        )

    with session_factory.begin() as session:
        reviews = session.scalars(select(DuplicateLegalIdentityReview)).all()

    assert reviews == []
