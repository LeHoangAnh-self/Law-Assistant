from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from qna_crawler.crawler import _crawl_id_range, extract_legal_citations, persist_government_qna_item
from qna_crawler.db import init_db
from qna_crawler.models import GovernmentQnaCitation, GovernmentQnaItem, LegalDocument
from qna_crawler.retrieval_audit import audit_qna_retrieval_readiness


def test_extract_legal_citations_finds_numbered_and_named_laws() -> None:
    text = (
        "Căn cứ Điều 89 Luật Xây dựng năm 2014 và Điều 6 khoản 2 điểm a Nghị định số "
        "15/2021/NĐ-CP về quản lý dự án đầu tư xây dựng."
    )

    citations = extract_legal_citations(text)

    assert any(citation.document_title == "Luật Xây dựng năm 2014" for citation in citations)
    numbered = [citation for citation in citations if citation.document_number == "15/2021/NĐ-CP"]
    assert len(numbered) == 1
    assert "Điều 6" in numbered[0].article_refs
    assert "khoản 2" in numbered[0].clause_refs
    assert "điểm a" in numbered[0].point_refs


def test_persist_government_qna_matches_existing_document_by_number() -> None:
    qna_engine = create_engine("sqlite:///:memory:")
    document_engine = create_engine("sqlite:///:memory:")
    init_db(qna_engine)
    LegalDocument.__table__.create(document_engine)
    qna_session_factory = sessionmaker(bind=qna_engine, expire_on_commit=False)
    document_session_factory = sessionmaker(bind=document_engine, expire_on_commit=False)

    with document_session_factory.begin() as session:
        session.add(
            LegalDocument(
                id=1502021,
                title="Nghị định 15/2021/NĐ-CP",
                document_number="15/2021/NĐ-CP",
                source="https://vbpl.vn/doc--1502021",
            )
        )

    qna = {
        "external_id": 22380,
        "source_name": "bachkhoaluat_hoi_dap_nha_nuoc",
        "source_url": "https://bachkhoaluat.vn/cam-nang/22380/test",
        "detail_url": "https://bachkhoaluat.vn/cam-nang/22380/test",
        "original_url": "https://baochinhphu.vn/test.htm",
        "title": "Có cần xin giấy phép xây dựng không?",
        "question_text": "Có cần xin giấy phép xây dựng không?",
        "answer_text": "Thực hiện theo Điều 6 Nghị định số 15/2021/NĐ-CP.",
        "summary_text": None,
        "responding_authority": "Bộ Xây dựng",
        "category_name": "Đất đai",
        "tags": "Giấy phép xây dựng",
        "published_date": date(2026, 6, 5),
        "source_payload": {"id": 22380},
    }
    citations = extract_legal_citations(qna["answer_text"])

    with qna_session_factory.begin() as qna_session:
        with document_session_factory() as document_session:
            item = persist_government_qna_item(qna_session, document_session, qna, citations)
        assert item.citation_status == "ALL_MATCHED"
        assert item.matched_citation_count == 1

    with qna_session_factory.begin() as session:
        persisted_item = session.scalar(select(GovernmentQnaItem))
        persisted_citation = session.scalar(select(GovernmentQnaCitation))

    assert persisted_item is not None
    assert persisted_item.external_id == 22380
    assert persisted_citation is not None
    assert persisted_citation.match_status == "MATCHED"
    assert persisted_citation.matched_document_id == 1502021
    assert persisted_citation.matched_document_number == "15/2021/NĐ-CP"
    assert persisted_citation.article_refs == "Điều 6"


def test_audit_retrieval_readiness_checks_qdrant_article_clause_point_payloads() -> None:
    qna_engine = create_engine("sqlite:///:memory:")
    document_engine = create_engine("sqlite:///:memory:")
    init_db(qna_engine)
    LegalDocument.__table__.create(document_engine)
    qna_session_factory = sessionmaker(bind=qna_engine, expire_on_commit=False)
    document_session_factory = sessionmaker(bind=document_engine, expire_on_commit=False)

    with document_session_factory.begin() as session:
        session.add(
            LegalDocument(
                id=1502021,
                title="Nghị định 15/2021/NĐ-CP",
                document_number="15/2021/NĐ-CP",
                source="https://vbpl.vn/doc--1502021",
            )
        )

    qna = {
        "external_id": 22380,
        "source_name": "bachkhoaluat_hoi_dap_nha_nuoc",
        "source_url": "https://bachkhoaluat.vn/cam-nang/22380/test",
        "title": "Có cần xin giấy phép xây dựng không?",
        "answer_text": "Thực hiện theo Điều 6 khoản 2 điểm a Nghị định số 15/2021/NĐ-CP.",
        "source_payload": {},
    }
    with qna_session_factory.begin() as qna_session:
        with document_session_factory() as document_session:
            persist_government_qna_item(qna_session, document_session, qna, extract_legal_citations(qna["answer_text"]))

    class FakeQdrantClient:
        def scroll_document_payloads(self, document_id: int):
            assert document_id == 1502021
            return [
                {
                    "document_id": 1502021,
                    "article_number": "6",
                    "clause_number": "2",
                    "point_number": "a",
                    "legal_path": "Điều 6 > khoản 2 > điểm a",
                    "text": "Điều 6. ... 2. ... a) ...",
                }
            ]

    summary = audit_qna_retrieval_readiness(qna_engine, FakeQdrantClient(), progress_every=0)

    assert summary.checked_citations == 1
    assert summary.ready_citations == 1
    assert summary.document_not_indexed == 0


def test_persist_government_qna_keeps_missing_document_as_benchmark_gap() -> None:
    qna_engine = create_engine("sqlite:///:memory:")
    document_engine = create_engine("sqlite:///:memory:")
    init_db(qna_engine)
    LegalDocument.__table__.create(document_engine)
    qna_session_factory = sessionmaker(bind=qna_engine, expire_on_commit=False)
    document_session_factory = sessionmaker(bind=document_engine, expire_on_commit=False)
    qna = {
        "external_id": 1,
        "source_name": "bachkhoaluat_hoi_dap_nha_nuoc",
        "source_url": "https://bachkhoaluat.vn/cam-nang/1/test",
        "title": "Test",
        "answer_text": "Theo Nghị định số 100/2024/NĐ-CP.",
        "source_payload": {},
    }

    with qna_session_factory.begin() as qna_session:
        with document_session_factory() as document_session:
            item = persist_government_qna_item(
                qna_session,
                document_session,
                qna,
                extract_legal_citations(qna["answer_text"]),
            )

    assert item.citation_status == "HAS_MISSING"
    assert item.missing_citation_count == 1


def test_id_range_discovery_skips_missing_and_non_qna(monkeypatch) -> None:
    qna_engine = create_engine("sqlite:///:memory:")
    document_engine = create_engine("sqlite:///:memory:")
    init_db(qna_engine)
    LegalDocument.__table__.create(document_engine)
    qna_session_factory = sessionmaker(bind=qna_engine, expire_on_commit=False)
    document_session_factory = sessionmaker(bind=document_engine, expire_on_commit=False)

    details = {
        3: {"id": 3, "idFeature": 12, "tieuDe": "Not Q&A"},
        2: None,
        1: {"id": 1, "idFeature": 74, "tieuDe": "Q&A", "tieuDeKhongDau": "q-a"},
    }

    monkeypatch.setattr("qna_crawler.crawler._fetch_bachkhoaluat_detail_optional", lambda http, settings, external_id: details[external_id])
    monkeypatch.setattr(
        "qna_crawler.crawler._build_qna_payload_from_detail",
        lambda http, settings, detail: {
            "external_id": detail["id"],
            "source_name": "bachkhoaluat_hoi_dap_nha_nuoc",
            "source_url": f"https://bachkhoaluat.vn/cam-nang/{detail['id']}/q-a",
            "title": detail["tieuDe"],
            "answer_text": "Theo Nghị định số 100/2024/NĐ-CP.",
            "source_payload": detail,
        },
    )

    summary = _crawl_id_range(
        qna_session_factory,
        document_session_factory,
        http=None,
        settings=None,
        id_start=3,
        id_end=1,
        limit=None,
        delay_seconds=0,
        require_answer=True,
        progress_every=0,
        max_consecutive_misses=None,
    )

    assert summary.checked == 3
    assert summary.fetched == 1
    assert summary.persisted == 1
    assert summary.non_qna == 1
    assert summary.not_found == 1
