from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from qna_crawler.config import Settings
from qna_crawler.models import GovernmentQnaCitation, GovernmentQnaItem, LegalDocument


LOGGER = logging.getLogger(__name__)

BACHKHOALUAT_API_BASE_URL = "https://api.bachkhoaluat.vn/api"
BACHKHOALUAT_SITE_BASE_URL = "https://bachkhoaluat.vn"
BACHKHOALUAT_QNA_FEATURE_ID = "74"
GOVERNMENT_QNA_SOURCE_NAME = "bachkhoaluat_hoi_dap_nha_nuoc"

DOCUMENT_NUMBER_RE = re.compile(
    r"\b\d{1,4}/\d{4}/[A-ZĐÂÊÔƠƯ0-9.-]+(?:-[A-ZĐÂÊÔƠƯ0-9.-]+)*\b",
    re.IGNORECASE,
)
ARTICLE_REF_RE = re.compile(r"\bĐiều\s+\d+[a-zA-Z]?", re.IGNORECASE)
CLAUSE_REF_RE = re.compile(r"\bkhoản\s+\d+[a-zA-Z]?", re.IGNORECASE)
POINT_REF_RE = re.compile(r"\bđiểm\s+[a-zđ]", re.IGNORECASE)
NUMBERED_DOC_RE = re.compile(
    r"(?P<raw>(?P<type>Luật|Bộ luật|Nghị định|Thông tư liên tịch|Thông tư|Quyết định|Nghị quyết|Công văn|Pháp lệnh)"
    r"[^.;:\n]{0,120}?\b(?:số\s+)?(?P<number>\d{1,4}/\d{4}/[A-ZĐÂÊÔƠƯ0-9.-]+(?:-[A-ZĐÂÊÔƠƯ0-9.-]+)*)"
    r"[^.;\n]{0,120})",
    re.IGNORECASE,
)
NAMED_LAW_RE = re.compile(
    r"(?P<raw>\b(?:Luật|Bộ luật)\s+[A-ZÀ-Ỹa-zà-ỹ0-9 ,()/-]{3,120}?\s+năm\s+\d{4}"
    r"|\b(?:Luật|Bộ luật)\s+[A-ZÀ-Ỹa-zà-ỹ0-9 ,()/-]{3,80})"
)
ANSWER_MARKER_RE = re.compile(
    r"\b(?:Bộ|Sở|Cục|Tổng cục|Ủy ban nhân dân|BHXH|Bảo hiểm xã hội)[^.\n]{0,120}trả lời",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class QnaCrawlSummary:
    checked: int = 0
    fetched: int = 0
    persisted: int = 0
    skipped: int = 0
    failed: int = 0
    non_qna: int = 0
    not_found: int = 0
    citations: int = 0
    matched_citations: int = 0
    missing_citations: int = 0


@dataclass(frozen=True)
class ParsedCitation:
    raw_text: str
    document_number: str | None
    document_title: str | None
    article_refs: tuple[str, ...]
    clause_refs: tuple[str, ...] = ()
    point_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CitationMatch:
    document_id: int | None
    status: str
    reason: str | None
    document_title: str | None = None
    document_number: str | None = None
    document_source: str | None = None


def crawl_bachkhoaluat_government_qna(
    qna_session_factory: sessionmaker[Session],
    document_session_factory: sessionmaker[Session],
    settings: Settings,
    *,
    cookie_file: str | None = None,
    limit: int | None = None,
    delay_seconds: float = 0.25,
    require_answer: bool = True,
    progress_every: int = 25,
    discovery_mode: str = "listing",
    id_start: int | None = None,
    id_end: int | None = None,
    max_consecutive_misses: int | None = None,
) -> QnaCrawlSummary:
    http = _create_http_session(settings, cookie_file)
    if discovery_mode == "listing":
        api_items = _fetch_bachkhoaluat_qna_listing(http, settings, limit=limit)
        _print_progress(f"Fetched Q&A listing: {len(api_items):,} items")
        return _crawl_api_items(
            qna_session_factory,
            document_session_factory,
            http,
            settings,
            api_items,
            delay_seconds=delay_seconds,
            require_answer=require_answer,
            progress_every=progress_every,
        )
    if discovery_mode == "id-range":
        return _crawl_id_range(
            qna_session_factory,
            document_session_factory,
            http,
            settings,
            id_start=id_start,
            id_end=id_end,
            limit=limit,
            delay_seconds=delay_seconds,
            require_answer=require_answer,
            progress_every=progress_every,
            max_consecutive_misses=max_consecutive_misses,
        )
    raise ValueError(f"Unsupported discovery_mode: {discovery_mode}")


def _crawl_api_items(
    qna_session_factory: sessionmaker[Session],
    document_session_factory: sessionmaker[Session],
    http: requests.Session,
    settings: Settings,
    api_items: list[dict[str, Any]],
    *,
    delay_seconds: float,
    require_answer: bool,
    progress_every: int,
) -> QnaCrawlSummary:
    summary = QnaCrawlSummary(fetched=len(api_items))
    for index, item in enumerate(api_items, start=1):
        try:
            qna = _build_qna_payload_from_listing_item(http, settings, item)
            if require_answer and not qna.get("answer_text"):
                summary = _add_summary(summary, checked=1, skipped=1)
                LOGGER.warning("Skipping Q&A id=%s because answer text could not be fetched", item.get("id"))
                continue
            summary = _persist_qna_payload(qna_session_factory, document_session_factory, qna, _add_summary(summary, checked=1))
        except Exception as exc:
            summary = _add_summary(summary, checked=1, failed=1)
            LOGGER.exception("Failed to crawl Q&A id=%s: %s", item.get("id"), exc)
        if progress_every > 0 and (index == 1 or index % progress_every == 0 or index == len(api_items)):
            _print_crawl_progress(index, len(api_items), summary)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return summary


def _crawl_id_range(
    qna_session_factory: sessionmaker[Session],
    document_session_factory: sessionmaker[Session],
    http: requests.Session,
    settings: Settings,
    *,
    id_start: int | None,
    id_end: int | None,
    limit: int | None,
    delay_seconds: float,
    require_answer: bool,
    progress_every: int,
    max_consecutive_misses: int | None,
) -> QnaCrawlSummary:
    if id_start is None:
        id_start = _latest_bachkhoaluat_qna_id(http, settings)
    if id_end is None:
        id_end = 1
    step = -1 if id_start >= id_end else 1
    total_ids = abs(id_start - id_end) + 1
    _print_progress(f"Scanning detail IDs from {id_start:,} to {id_end:,} ({total_ids:,} ids)")

    summary = QnaCrawlSummary()
    consecutive_misses = 0
    persisted_limit = limit if limit is not None and limit > 0 else None

    for index, external_id in enumerate(range(id_start, id_end + step, step), start=1):
        if persisted_limit is not None and summary.persisted >= persisted_limit:
            _print_progress(f"Stopping after persisted limit: {persisted_limit:,}")
            break
        if max_consecutive_misses is not None and consecutive_misses >= max_consecutive_misses:
            _print_progress(f"Stopping after {consecutive_misses:,} consecutive missing/non-Q&A IDs")
            break
        try:
            detail = _fetch_bachkhoaluat_detail_optional(http, settings, external_id)
            summary = _add_summary(summary, checked=1)
            if detail is None:
                consecutive_misses += 1
                summary = _add_summary(summary, not_found=1)
            elif str(detail.get("idFeature")) != BACHKHOALUAT_QNA_FEATURE_ID:
                consecutive_misses += 1
                summary = _add_summary(summary, non_qna=1)
            else:
                consecutive_misses = 0
                qna = _build_qna_payload_from_detail(http, settings, detail)
                if require_answer and not qna.get("answer_text"):
                    summary = _add_summary(summary, fetched=1, skipped=1)
                    LOGGER.warning("Skipping Q&A id=%s because answer text could not be fetched", external_id)
                else:
                    summary = _add_summary(summary, fetched=1)
                    summary = _persist_qna_payload(qna_session_factory, document_session_factory, qna, summary)
        except Exception as exc:
            consecutive_misses = 0
            summary = _add_summary(summary, checked=1, failed=1)
            LOGGER.exception("Failed to crawl detail id=%s: %s", external_id, exc)
        if progress_every > 0 and (index == 1 or index % progress_every == 0):
            _print_crawl_progress(index, total_ids, summary)
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return summary


def _persist_qna_payload(
    qna_session_factory: sessionmaker[Session],
    document_session_factory: sessionmaker[Session],
    qna: dict[str, Any],
    summary: QnaCrawlSummary,
) -> QnaCrawlSummary:
    citations = extract_legal_citations(
        "\n".join(
            value
            for value in (qna.get("question_text"), qna.get("answer_text"), qna.get("summary_text"))
            if value
        )
    )
    with qna_session_factory.begin() as qna_session:
        with document_session_factory() as document_session:
            qna_item = persist_government_qna_item(qna_session, document_session, qna, citations)
        return _add_summary(
            summary,
            checked=0,
            persisted=1,
            citations=qna_item.citation_count,
            matched_citations=qna_item.matched_citation_count,
            missing_citations=qna_item.missing_citation_count,
        )


def persist_government_qna_item(
    qna_session: Session,
    document_session: Session,
    qna: dict[str, Any],
    citations: list[ParsedCitation],
) -> GovernmentQnaItem:
    source_url = str(qna["source_url"])
    source_url_hash = _sha256(source_url)
    content_hash = _sha256("\n".join(str(qna.get(key) or "") for key in ("question_text", "answer_text", "summary_text")))

    item = qna_session.scalar(select(GovernmentQnaItem).where(GovernmentQnaItem.source_url_hash == source_url_hash))
    if item is None:
        item = GovernmentQnaItem(source_url=source_url, source_url_hash=source_url_hash, title=str(qna["title"]))
        qna_session.add(item)

    item.external_id = _safe_int(qna.get("external_id"))
    item.source_name = str(qna.get("source_name") or GOVERNMENT_QNA_SOURCE_NAME)
    item.detail_url = qna.get("detail_url")
    item.original_url = qna.get("original_url")
    item.title = str(qna["title"])
    item.question_text = qna.get("question_text")
    item.answer_text = qna.get("answer_text")
    item.answer_html = qna.get("answer_html")
    item.summary_text = qna.get("summary_text")
    item.responding_authority = qna.get("responding_authority")
    item.category_name = qna.get("category_name")
    item.tags = qna.get("tags")
    item.published_date = qna.get("published_date")
    item.source_payload_json = json.dumps(qna.get("source_payload") or {}, ensure_ascii=False, sort_keys=True)
    item.content_hash = content_hash
    qna_session.flush()

    qna_session.execute(delete(GovernmentQnaCitation).where(GovernmentQnaCitation.qna_item_id == item.id))
    seen_hashes: set[str] = set()
    matched_count = 0
    missing_count = 0
    for citation in citations:
        citation_hash = _sha256(_normalize_text(citation.raw_text))[:64]
        if citation_hash in seen_hashes:
            continue
        seen_hashes.add(citation_hash)
        match = _match_cited_document(document_session, citation)
        if match.status == "MATCHED":
            matched_count += 1
        elif match.status == "MISSING":
            missing_count += 1
        qna_session.add(
            GovernmentQnaCitation(
                qna_item_id=item.id,
                citation_hash=citation_hash,
                raw_text=citation.raw_text,
                document_number=citation.document_number,
                document_title=citation.document_title,
                article_refs=", ".join(citation.article_refs) or None,
                clause_refs=", ".join(citation.clause_refs) or None,
                point_refs=", ".join(citation.point_refs) or None,
                matched_document_id=match.document_id,
                matched_document_title=match.document_title,
                matched_document_number=match.document_number,
                matched_document_source=match.document_source,
                match_status=match.status,
                match_reason=match.reason,
            )
        )

    item.citation_count = len(seen_hashes)
    item.matched_citation_count = matched_count
    item.missing_citation_count = missing_count
    if item.citation_count == 0:
        item.citation_status = "NO_CITATIONS"
    elif missing_count > 0:
        item.citation_status = "HAS_MISSING"
    elif matched_count == item.citation_count:
        item.citation_status = "ALL_MATCHED"
    else:
        item.citation_status = "PARTIAL"
    qna_session.flush()
    return item


def extract_legal_citations(text: str) -> list[ParsedCitation]:
    citations: list[ParsedCitation] = []
    occupied_spans: list[tuple[int, int]] = []
    for match in NUMBERED_DOC_RE.finditer(text):
        raw, span = _isolate_numbered_citation(text, match)
        if not raw:
            continue
        occupied_spans.append(span)
        citations.append(
            ParsedCitation(
                raw_text=raw,
                document_number=_normalize_document_number(match.group("number")),
                document_title=_infer_document_title(raw),
                article_refs=tuple(_extract_article_refs_nearby(text, match.start(), match.end())),
                clause_refs=tuple(_extract_clause_refs_nearby(text, match.start(), match.end())),
                point_refs=tuple(_extract_point_refs_nearby(text, match.start(), match.end())),
            )
        )

    for match in NAMED_LAW_RE.finditer(text):
        if any(match.start() >= start and match.end() <= end for start, end in occupied_spans):
            continue
        raw = _clean_citation_text(match.group("raw"))
        title = _infer_document_title(raw)
        if not raw or not title or len(title) < 8:
            continue
        citations.append(
            ParsedCitation(
                raw_text=raw,
                document_number=None,
                document_title=title,
                article_refs=tuple(_extract_article_refs_nearby(text, match.start(), match.end())),
                clause_refs=tuple(_extract_clause_refs_nearby(text, match.start(), match.end())),
                point_refs=tuple(_extract_point_refs_nearby(text, match.start(), match.end())),
            )
        )

    deduped: dict[str, ParsedCitation] = {}
    for citation in citations:
        key = _normalize_text(citation.document_number or citation.document_title or citation.raw_text)
        if key and key not in deduped:
            deduped[key] = citation
    return list(deduped.values())


def _build_qna_payload_from_listing_item(http: requests.Session, settings: Settings, item: dict[str, Any]) -> dict[str, Any]:
    detail = _fetch_bachkhoaluat_detail(http, settings, int(item["id"]))
    data = {**item, **detail}
    return _build_qna_payload_from_detail(http, settings, data)


def _build_qna_payload_from_detail(http: requests.Session, settings: Settings, data: dict[str, Any]) -> dict[str, Any]:
    detail_url = _bachkhoaluat_detail_url(data)
    original_url = data.get("linkTrichDan")
    source_page = _fetch_government_source_page(http, settings, original_url) if original_url else {}
    docx_text = ""
    if not source_page.get("answer_text") and data.get("linkDownLoadWord"):
        docx_text = _fetch_docx_text(http, settings, data["linkDownLoadWord"])

    source_question = source_page.get("question_text")
    source_answer = source_page.get("answer_text") or docx_text or None
    summary = data.get("noiDungNgan") or data.get("moTaNgan")
    question = source_question or summary
    return {
        "external_id": data.get("id"),
        "source_name": GOVERNMENT_QNA_SOURCE_NAME,
        "source_url": detail_url,
        "detail_url": detail_url,
        "original_url": original_url,
        "title": data.get("tieuDe") or source_page.get("title") or f"Government Q&A {data.get('id')}",
        "question_text": _clean_body_text(question),
        "answer_text": _clean_body_text(source_answer),
        "answer_html": source_page.get("answer_html"),
        "summary_text": _clean_body_text(summary),
        "responding_authority": data.get("coQuanTraLoi"),
        "category_name": data.get("categoryName"),
        "tags": data.get("hashTag"),
        "published_date": _parse_vietnamese_date(data.get("ngayDang")),
        "source_payload": data,
    }


def _fetch_bachkhoaluat_qna_listing(
    http: requests.Session,
    settings: Settings,
    *,
    limit: int | None,
) -> list[dict[str, Any]]:
    requested_limit = max(1, limit or 1)
    first_payload = _get_json(
        http,
        f"{BACHKHOALUAT_API_BASE_URL}/businessEssential",
        settings,
        params={"cmcndn": BACHKHOALUAT_QNA_FEATURE_ID, "limit": requested_limit},
    )
    data = first_payload.get("data") or {}
    total = _safe_int(data.get("count")) or len(data.get("result") or [])
    if limit is None and total > requested_limit:
        first_payload = _get_json(
            http,
            f"{BACHKHOALUAT_API_BASE_URL}/businessEssential",
            settings,
            params={"cmcndn": BACHKHOALUAT_QNA_FEATURE_ID, "limit": total},
        )
        data = first_payload.get("data") or {}
    items = list(data.get("result") or [])
    if limit is None and total > len(items):
        _print_progress(
            f"Warning: BachKhoaLuat listing API returned {len(items):,}/{total:,} items. "
            "The endpoint appears capped; this run will crawl only returned listing items."
        )
    return items[:limit] if limit is not None else items


def _fetch_bachkhoaluat_detail(http: requests.Session, settings: Settings, external_id: int) -> dict[str, Any]:
    payload = _get_json(
        http,
        f"{BACHKHOALUAT_API_BASE_URL}/businessEssential/business-essential/{external_id}",
        settings,
    )
    return payload.get("data") or {}


def _fetch_bachkhoaluat_detail_optional(
    http: requests.Session,
    settings: Settings,
    external_id: int,
) -> dict[str, Any] | None:
    url = f"{BACHKHOALUAT_API_BASE_URL}/businessEssential/business-essential/{external_id}"
    response = http.get(url, headers=_headers(settings, accept="application/json"), timeout=settings.timeout_seconds)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") == 404:
        return None
    if payload.get("status") not in (None, 200):
        raise RuntimeError(f"BachKhoaLuat detail returned status={payload.get('status')} message={payload.get('message')}")
    return payload.get("data") or None


def _latest_bachkhoaluat_qna_id(http: requests.Session, settings: Settings) -> int:
    items = _fetch_bachkhoaluat_qna_listing(http, settings, limit=1)
    if not items:
        raise RuntimeError("Could not discover latest Q&A id from listing endpoint")
    latest_id = _safe_int(items[0].get("id"))
    if latest_id is None:
        raise RuntimeError(f"Latest Q&A listing item has invalid id: {items[0].get('id')!r}")
    return latest_id


def _fetch_government_source_page(http: requests.Session, settings: Settings, url: str | None) -> dict[str, str | None]:
    if not url:
        return {}
    response = http.get(url, headers=_headers(settings, accept="text/html"), timeout=settings.timeout_seconds)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    title = _first_text(soup.select("h1, .detail-title"))
    content = soup.select_one(".detail-content")
    if content is None:
        return {"title": title, "question_text": None, "answer_text": None, "answer_html": None}
    for removable in content.select("script, style, .VCSortableInPreviewMode"):
        removable.decompose()
    body_text = _clean_body_text(content.get_text("\n", strip=True)) or ""
    question_text, answer_text = _split_question_answer(body_text)
    return {
        "title": title,
        "question_text": question_text,
        "answer_text": answer_text,
        "answer_html": str(content),
    }


def _fetch_docx_text(http: requests.Session, settings: Settings, url: str) -> str:
    response = http.get(url, headers=_headers(settings), timeout=settings.timeout_seconds)
    response.raise_for_status()
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        xml_content = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_content)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        texts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        joined = _clean_body_text("".join(texts))
        if joined:
            paragraphs.append(joined)
    return "\n".join(paragraphs)


def _split_question_answer(text: str) -> tuple[str | None, str | None]:
    marker = ANSWER_MARKER_RE.search(text)
    if not marker:
        return text or None, None
    question = text[: marker.start()].strip()
    answer = text[marker.start() :].strip()
    return question or None, answer or None


def _match_cited_document(session: Session, citation: ParsedCitation) -> CitationMatch:
    if citation.document_number:
        number_prefix = citation.document_number.split("/", 1)[0]
        possible_candidates = session.scalars(
            select(LegalDocument).where(LegalDocument.document_number.like(f"{number_prefix}/%"))
        ).all()
        candidates = [
            document
            for document in possible_candidates
            if _normalize_document_number(document.document_number) == citation.document_number
        ]
        if len(candidates) == 1:
            return _matched_document(candidates[0], "EXACT_DOCUMENT_NUMBER")
        if len(candidates) > 1:
            return CitationMatch(None, "AMBIGUOUS", "DOCUMENT_NUMBER_MATCHED_MULTIPLE_ROWS")
        return CitationMatch(None, "MISSING", "DOCUMENT_NUMBER_NOT_FOUND")

    if citation.document_title:
        title = citation.document_title.strip()
        candidates = session.scalars(
            select(LegalDocument)
            .where(or_(LegalDocument.title.ilike(f"%{title}%"), LegalDocument.document_type.ilike(f"%{title}%")))
            .limit(5)
        ).all()
        if len(candidates) == 1:
            return _matched_document(candidates[0], "TITLE_HINT_MATCH")
        if len(candidates) > 1:
            return CitationMatch(None, "AMBIGUOUS", "TITLE_HINT_MATCHED_MULTIPLE_ROWS")
    return CitationMatch(None, "UNRESOLVED", "NO_DOCUMENT_NUMBER")


def _matched_document(document: LegalDocument, reason: str) -> CitationMatch:
    return CitationMatch(
        document_id=int(document.id),
        status="MATCHED",
        reason=reason,
        document_title=document.title,
        document_number=document.document_number,
        document_source=document.source,
    )


def _create_http_session(settings: Settings, cookie_file: str | None) -> requests.Session:
    session = requests.Session()
    session.headers.update(_headers(settings))
    if cookie_file:
        _load_browser_cookies(session, cookie_file)
    return session


def _load_browser_cookies(session: requests.Session, cookie_file: str) -> None:
    path = Path(cookie_file).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Cookie file does not exist: {path}")
    cookies = json.loads(path.read_text(encoding="utf-8"))
    for cookie in cookies:
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path") or "/",
        )


def _get_json(http: requests.Session, url: str, settings: Settings, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = http.get(url, params=params, headers=_headers(settings, accept="application/json"), timeout=settings.timeout_seconds)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") not in (None, 200):
        raise RuntimeError(f"BachKhoaLuat API returned status={payload.get('status')} message={payload.get('message')}")
    return payload


def _bachkhoaluat_detail_url(data: dict[str, Any]) -> str:
    slug = data.get("tieuDeKhongDau") or ""
    return urljoin(BACHKHOALUAT_SITE_BASE_URL, f"/cam-nang/{data.get('id')}/{quote(slug)}")


def _headers(settings: Settings, *, accept: str = "application/json, text/plain, */*") -> dict[str, str]:
    return {"User-Agent": settings.user_agent, "Accept": accept}


def _parse_vietnamese_date(value: Any) -> date | None:
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def _first_text(elements) -> str | None:
    for element in elements:
        text = _clean_body_text(element.get_text(" ", strip=True))
        if text:
            return text
    return None


def _extract_article_refs_nearby(text: str, start: int, end: int) -> list[str]:
    window = text[max(0, start - 120) : min(len(text), end + 80)]
    return list(dict.fromkeys(_clean_citation_text(match.group(0)) for match in ARTICLE_REF_RE.finditer(window)))


def _extract_clause_refs_nearby(text: str, start: int, end: int) -> list[str]:
    window = text[max(0, start - 120) : min(len(text), end + 80)]
    return list(dict.fromkeys(_clean_citation_text(match.group(0)) for match in CLAUSE_REF_RE.finditer(window)))


def _extract_point_refs_nearby(text: str, start: int, end: int) -> list[str]:
    window = text[max(0, start - 120) : min(len(text), end + 80)]
    return list(dict.fromkeys(_clean_citation_text(match.group(0)) for match in POINT_REF_RE.finditer(window)))


def _infer_document_title(raw: str) -> str | None:
    cleaned = _clean_citation_text(DOCUMENT_NUMBER_RE.sub("", raw))
    cleaned = re.sub(r"\b(số|của|ngày|được|sửa đổi|bổ sung)\b.*$", "", cleaned, flags=re.IGNORECASE).strip(" ,.-")
    return cleaned or None


def _isolate_numbered_citation(text: str, match: re.Match[str]) -> tuple[str, tuple[int, int]]:
    raw = match.group("raw")
    number = match.group("number")
    number_index = raw.casefold().find(number.casefold())
    prefix = raw[:number_index] if number_index >= 0 else raw
    keyword_matches = list(
        re.finditer(
            r"\b(Luật|Bộ luật|Nghị định|Thông tư liên tịch|Thông tư|Quyết định|Nghị quyết|Công văn|Pháp lệnh)\b",
            prefix,
            re.IGNORECASE,
        )
    )
    start_offset = keyword_matches[-1].start() if keyword_matches else 0
    isolated = raw[start_offset:]
    start = match.start("raw") + start_offset
    return _clean_citation_text(isolated), (start, match.end("raw"))


def _normalize_document_number(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", "", value).strip(".,;:)")
    return normalized.upper()


def _clean_citation_text(value: str | None) -> str:
    value = html.unescape(value or "")
    return " ".join(value.replace("\xa0", " ").split()).strip(" ,.;:")


def _clean_body_text(value: str | None) -> str | None:
    cleaned = _clean_citation_text(value)
    return cleaned or None


def _normalize_text(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _add_summary(summary: QnaCrawlSummary, **updates: int) -> QnaCrawlSummary:
    values = summary.__dict__.copy()
    for key, value in updates.items():
        values[key] += value
    return QnaCrawlSummary(**values)


def _print_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _print_crawl_progress(index: int, total: int, summary: QnaCrawlSummary) -> None:
    _print_progress(
        f"Processed {index:,}/{total:,}: checked={summary.checked:,} fetched={summary.fetched:,} "
        f"persisted={summary.persisted:,} skipped={summary.skipped:,} failed={summary.failed:,} "
        f"not_found={summary.not_found:,} non_qna={summary.non_qna:,} "
        f"citations={summary.citations:,} matched={summary.matched_citations:,} "
        f"missing={summary.missing_citations:,}"
    )
