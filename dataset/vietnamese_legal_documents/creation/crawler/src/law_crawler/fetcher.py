from __future__ import annotations

import csv
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from law_crawler.config import Settings
from law_crawler.pdf_ocr import (
    extract_pdf_ocr_paragraphs,
    extract_pdf_text_paragraphs,
    paragraphs_to_html,
)


LOGGER = logging.getLogger(__name__)
ITEM_ID_RE = re.compile(r"ItemID=(\d+)", re.IGNORECASE)
DETAIL_ID_RE = re.compile(r"--(\d+)(?:[/?#]|$)")
TVPL_DOCUMENT_RE = re.compile(r"/van-ban/.+\.aspx(?:[?#].*)?$", re.IGNORECASE)
TVPL_STOPWORDS = {
    "ban",
    "chi",
    "dieu",
    "duoc",
    "quy",
    "so",
    "tiet",
    "van",
    "ve",
    "va",
}


@dataclass(frozen=True)
class FetchedDocument:
    document_id: int
    source_url: str
    html: str
    content_source: str = "API_HTML"
    pdf_file_name: str | None = None
    title: str | None = None
    document_number: str | None = None
    document_type: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    expired_date: date | None = None
    validity_status: str | None = None
    issuing_authority: str | None = None
    relationships: tuple["FetchedRelationship", ...] = ()


@dataclass(frozen=True)
class FetchedRelationship:
    related_document_id: int
    relationship_type: str
    source_text: str | None = None


class FetchError(RuntimeError):
    pass


def fetch_vbpl_document(url: str, settings: Settings) -> FetchedDocument:
    _validate_url(url)
    item_id = _extract_item_id(url)
    headers = {"User-Agent": settings.user_agent}
    response = requests.get(url, headers=headers, timeout=settings.timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    fulltext = soup.find("div", class_="fulltext")
    if fulltext:
        content = fulltext.find(id="toanvancontent") or fulltext
    else:
        content = soup.find(id="toanvancontent")

    if content is None:
        LOGGER.warning("Could not find VBPL fulltext container for document_id=%s", item_id)
        raise FetchError("VBPL fulltext container was not found")

    return FetchedDocument(document_id=item_id, source_url=url, html=str(content))


def fetch_vbpl_document_by_id(document_id: int, source_url: str | None, settings: Settings) -> FetchedDocument:
    url = f"{settings.vbpl_api_base_url}/qtdc/public/doc/{document_id}"
    headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=settings.timeout_seconds)
        response.raise_for_status()
    except requests.HTTPError as exc:
        fallback = fetch_thuvienphapluat_fallback_document(document_id, source_url, settings)
        if fallback:
            LOGGER.info(
                "Fetched document_id=%s from thuvienphapluat.vn fallback after VBPL API HTTP %s",
                document_id,
                exc.response.status_code if exc.response is not None else "unknown",
            )
            return fallback
        raise
    payload = response.json()
    if not payload.get("success"):
        fallback = fetch_thuvienphapluat_fallback_document(document_id, source_url, settings)
        if fallback:
            LOGGER.info("Fetched document_id=%s from thuvienphapluat.vn fallback after VBPL API failure", document_id)
            return fallback
        raise FetchError(f"VBPL API did not return success for document_id={document_id}")

    data = payload.get("data") or {}
    content = (data.get("documentContent") or {}).get("content")
    content_source = "API_HTML"
    pdf_file_name = None
    if not content:
        pdf_file_name = data.get("documentContentFileName")
        pdf_content = _fetch_pdf_content_as_html(document_id, data, settings)
        if pdf_content:
            content, content_source = pdf_content
    if not content:
        raise FetchError(f"VBPL API document_id={document_id} has no full document content")

    doc_type = data.get("docType") or {}
    eff_status = data.get("effStatus") or {}
    organization = data.get("organization") or {}
    return FetchedDocument(
        document_id=int(data.get("id") or document_id),
        source_url=source_url or f"https://vbpl.vn/van-ban/chi-tiet/--{document_id}",
        html=content,
        content_source=content_source,
        pdf_file_name=pdf_file_name,
        title=data.get("title"),
        document_number=data.get("docNum"),
        document_type=doc_type.get("name") if isinstance(doc_type, dict) else None,
        issued_date=_parse_api_date(data.get("issueDate")),
        effective_date=_parse_api_date(data.get("effFrom")),
        expired_date=_parse_api_date(data.get("effTo")),
        validity_status=eff_status.get("name") if isinstance(eff_status, dict) else None,
        issuing_authority=data.get("agencyName") or organization.get("name"),
        relationships=tuple(_extract_relationships(data)),
    )


def fetch_thuvienphapluat_fallback_document(
    document_id: int,
    source_url: str | None,
    settings: Settings,
) -> FetchedDocument | None:
    fallback_url = _resolve_thuvienphapluat_fallback_url(document_id, source_url, settings)
    if not fallback_url:
        return None
    _validate_thuvienphapluat_url(fallback_url)

    headers = _thuvienphapluat_headers(settings, referer="https://www.google.com/")

    response = requests.get(fallback_url, headers=headers, timeout=settings.timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    content = _extract_thuvienphapluat_content(soup)
    if content is None:
        LOGGER.warning("Could not find thuvienphapluat.vn content container for document_id=%s", document_id)
        raise FetchError(f"Thuvienphapluat fallback document_id={document_id} has no full document content")

    title = _extract_thuvienphapluat_title(soup)
    return FetchedDocument(
        document_id=document_id,
        source_url=source_url or fallback_url,
        html=str(content),
        content_source="TVPL_HTML",
        title=title,
    )


def _resolve_thuvienphapluat_fallback_url(
    document_id: int,
    source_url: str | None,
    settings: Settings,
) -> str | None:
    mapped_url = _lookup_thuvienphapluat_fallback_url(document_id, settings)
    if mapped_url:
        return mapped_url
    if not source_url:
        return None
    return _search_thuvienphapluat_fallback_url(source_url, settings)


def _lookup_thuvienphapluat_fallback_url(document_id: int, settings: Settings) -> str | None:
    map_file = settings.thuvienphapluat_fallback_map_file
    if not map_file:
        return None

    with Path(map_file).open(newline="", encoding="utf-8") as handle:
        sample = handle.read(2048)
        handle.seek(0)
        has_header = "document_id" in sample.splitlines()[0].lower() if sample.splitlines() else False
        if has_header:
            for row in csv.DictReader(handle):
                if _safe_int(row.get("document_id")) == document_id:
                    return (row.get("url") or row.get("fallback_url") or "").strip() or None
            return None

        for row in csv.reader(handle):
            if len(row) < 2:
                continue
            if _safe_int(row[0]) == document_id:
                return row[1].strip() or None
    return None


def _search_thuvienphapluat_fallback_url(source_url: str, settings: Settings) -> str | None:
    query = _thuvienphapluat_query_from_source_url(source_url)
    if not query:
        return None

    headers = _thuvienphapluat_headers(settings)

    google_url = _search_google_thuvienphapluat_fallback_url(query, source_url, headers, settings)
    if google_url:
        return google_url

    search_urls = [
        f"https://thuvienphapluat.vn/page/tim-van-ban.aspx?keyword={quote_plus(query)}",
        f"https://thuvienphapluat.vn/tim-van-ban.aspx?keyword={quote_plus(query)}",
    ]
    for search_url in search_urls:
        try:
            response = requests.get(search_url, headers=headers, timeout=settings.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.warning("Thuvienphapluat fallback search failed url=%s error=%s", search_url, exc)
            continue

        best_url = _best_thuvienphapluat_search_result(response.content, source_url)
        if best_url:
            LOGGER.info("Resolved thuvienphapluat.vn fallback url=%s from source_url=%s", best_url, source_url)
            return best_url
    return None


def _search_google_thuvienphapluat_fallback_url(
    query: str,
    source_url: str,
    headers: dict[str, str],
    settings: Settings,
) -> str | None:
    google_query = f"site:thuvienphapluat.vn/van-ban {query}"
    search_url = f"https://www.google.com/search?q={quote_plus(google_query)}"
    google_headers = {
        **headers,
        "Accept-Language": "vi,en;q=0.8",
    }
    try:
        response = requests.get(search_url, headers=google_headers, timeout=settings.timeout_seconds)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("Google fallback search failed url=%s error=%s", search_url, exc)
        return None

    best_url = _best_google_thuvienphapluat_result(response.content, source_url)
    if best_url:
        LOGGER.info("Resolved thuvienphapluat.vn fallback url=%s from Google source_url=%s", best_url, source_url)
    return best_url


def _thuvienphapluat_headers(settings: Settings, *, referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
    cookie_header = _load_cookie_header(settings.thuvienphapluat_cookie_file)
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def _thuvienphapluat_query_from_source_url(source_url: str) -> str | None:
    parsed = urlparse(source_url)
    slug = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    slug = DETAIL_ID_RE.sub("", slug)
    return slug or None


def _extract_document_number_tokens(tokens: list[str]) -> list[str]:
    for index, token in enumerate(tokens):
        if token.isdigit() and index + 2 < len(tokens):
            year = tokens[index + 1]
            if len(year) == 4 and year.isdigit():
                tail = [candidate for candidate in tokens[index + 2 : index + 5] if len(candidate) >= 2]
                if tail:
                    return [token, year, *tail]
    return []


def _best_thuvienphapluat_search_result(html: bytes, source_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        absolute = urljoin("https://thuvienphapluat.vn", href)
        parsed = urlparse(absolute)
        if parsed.hostname not in {"thuvienphapluat.vn", "www.thuvienphapluat.vn"}:
            continue
        if not TVPL_DOCUMENT_RE.search(parsed.path):
            continue
        candidates[absolute] = _clean_container_text(link)

    if not candidates:
        return None

    scored = [
        (_thuvienphapluat_result_score(source_url, candidate_url, candidate_text), candidate_url)
        for candidate_url, candidate_text in candidates.items()
    ]
    score, url = max(scored, key=lambda item: item[0])
    return url if score >= 0.35 else None


def _best_google_thuvienphapluat_result(html: bytes, source_url: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        candidate_url = _extract_google_result_url(str(link["href"]))
        if not candidate_url:
            continue
        parsed = urlparse(candidate_url)
        if parsed.hostname not in {"thuvienphapluat.vn", "www.thuvienphapluat.vn"}:
            continue
        if not TVPL_DOCUMENT_RE.search(parsed.path):
            continue
        candidates[candidate_url] = _clean_container_text(link)

    if not candidates:
        return None

    scored = [
        (_thuvienphapluat_result_score(source_url, candidate_url, candidate_text), candidate_url)
        for candidate_url, candidate_text in candidates.items()
    ]
    score, url = max(scored, key=lambda item: item[0])
    return url if score >= 0.35 else None


def _extract_google_result_url(href: str) -> str | None:
    if href.startswith("/url?"):
        parsed = urlparse(href)
        values = parse_qs(parsed.query).get("q")
        if values:
            return values[0]
    if href.startswith("https://thuvienphapluat.vn/") or href.startswith("https://www.thuvienphapluat.vn/"):
        return href
    return None


def _thuvienphapluat_result_score(source_url: str, candidate_url: str, candidate_text: str) -> float:
    source_tokens = set(_normalized_tokens(source_url)) - TVPL_STOPWORDS
    candidate_tokens = set(_normalized_tokens(f"{candidate_url} {candidate_text}")) - TVPL_STOPWORDS
    if not source_tokens or not candidate_tokens:
        return 0.0

    overlap = len(source_tokens & candidate_tokens) / len(source_tokens)
    source_doc_number = _extract_document_number_tokens(list(_normalized_tokens(source_url)))
    if source_doc_number and all(token in candidate_tokens for token in source_doc_number[:2]):
        overlap += 0.35
    return overlap


def _normalized_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFD", value)
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = normalized.lower()
    return [token for token in re.split(r"[^a-z0-9]+", normalized) if token]


def _validate_thuvienphapluat_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FetchError("Only HTTP(S) URLs are supported")
    if parsed.hostname not in {"thuvienphapluat.vn", "www.thuvienphapluat.vn"}:
        raise FetchError("Only thuvienphapluat.vn fallback URLs are supported")


def _load_cookie_header(cookie_file: str | None) -> str | None:
    if not cookie_file:
        return None

    text = Path(cookie_file).read_text(encoding="utf-8").strip()
    if not text:
        return None

    if "=" in text and "\t" not in text and "\n" not in text:
        return text

    cookie_parts: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5].strip()
            value = parts[6].strip()
            if name:
                cookie_parts.append(f"{name}={value}")
            continue

        simple_cookie = SimpleCookie()
        try:
            simple_cookie.load(line)
        except Exception:
            continue
        for name, morsel in simple_cookie.items():
            cookie_parts.append(f"{name}={morsel.value}")

    return "; ".join(cookie_parts) or None


def _extract_thuvienphapluat_content(soup: BeautifulSoup) -> Tag | None:
    selectors = [
        "#divContentDoc",
        "#divNoiDung",
        "#divFullText",
        "#divContent",
        ".content1",
        ".contentdoc",
        ".content-doc",
        ".vanban-content",
        ".news-content",
        ".content-detail",
    ]
    for selector in selectors:
        element = soup.select_one(selector)
        if element and _clean_container_text(element):
            _remove_noise_tags(element)
            return element

    candidates = soup.find_all(["article", "section", "div"])
    if not candidates:
        return None
    best = max(candidates, key=lambda tag: len(_clean_container_text(tag)), default=None)
    if best is None or len(_clean_container_text(best)) < 500:
        return None
    _remove_noise_tags(best)
    return best


def _extract_thuvienphapluat_title(soup: BeautifulSoup) -> str | None:
    for selector in ["h1", ".title", ".doc-title", ".news-title"]:
        element = soup.select_one(selector)
        if element:
            text = _clean_container_text(element)
            if text:
                return text[:1500]

    meta_title = soup.select_one("meta[property='og:title']")
    if meta_title and meta_title.get("content"):
        return str(meta_title["content"]).strip()[:1500]

    if soup.title:
        text = _clean_container_text(soup.title)
        if text:
            return text[:1500]
    return None


def _remove_noise_tags(tag: Tag) -> None:
    for child in tag.find_all(["script", "style", "noscript", "iframe", "form"]):
        child.decompose()


def _clean_container_text(tag: Tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ")).strip()


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _extract_relationships(data: dict) -> list[FetchedRelationship]:
    relationships: list[FetchedRelationship] = []

    for ref in data.get("references") or []:
        target = ref.get("targetDocument") or {}
        target_id = target.get("id")
        if not target_id:
            continue
        try:
            related_document_id = int(target_id)
        except (TypeError, ValueError):
            continue
        reference_type = ref.get("referenceType")
        target_title = target.get("title")
        source_text = f"VBPL referenceType={reference_type}"
        if target_title:
            source_text = f"{source_text}; target={target_title}"
        relationships.append(
            FetchedRelationship(
                related_document_id=related_document_id,
                relationship_type="REFERENCES",
                source_text=source_text[:1000],
            )
        )

    for ref in data.get("documentRelatedList") or []:
        target_id = ref.get("id") or ref.get("documentId") or ref.get("targetDocumentId")
        if not target_id:
            continue
        try:
            related_document_id = int(target_id)
        except (TypeError, ValueError):
            continue
        relationships.append(
            FetchedRelationship(
                related_document_id=related_document_id,
                relationship_type="REFERENCES",
                source_text=str(ref)[:1000],
            )
        )

    return relationships


def _fetch_pdf_content_as_html(document_id: int, data: dict, settings: Settings) -> tuple[str, str] | None:
    file_name = data.get("documentContentFileName")
    if not file_name or not str(file_name).lower().endswith(".pdf"):
        return None

    url = f"{settings.vbpl_api_base_url}/qtdc/public/doc/minio/buckets/vbpl/{document_id}/{file_name}/download"
    response = requests.get(
        url,
        headers={"User-Agent": settings.user_agent, "Accept": "application/pdf,*/*"},
        timeout=settings.timeout_seconds,
    )
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        LOGGER.warning("VBPL document_id=%s file=%s did not return a PDF", document_id, file_name)
        return None

    paragraphs = extract_pdf_text_paragraphs(response.content)
    content_source = "PDF_TEXT"
    text_length = sum(len(paragraph) for paragraph in paragraphs)
    if text_length < settings.pdf_text_min_chars:
        if settings.enable_pdf_ocr:
            ocr_paragraphs = extract_pdf_ocr_paragraphs(response.content, settings)
            if sum(len(paragraph) for paragraph in ocr_paragraphs) > text_length:
                paragraphs = ocr_paragraphs
                content_source = "PDF_OCR"
        else:
            LOGGER.info(
                "VBPL document_id=%s PDF text length %s is below threshold %s; OCR disabled",
                document_id,
                text_length,
                settings.pdf_text_min_chars,
            )

    if not paragraphs:
        LOGGER.warning("VBPL document_id=%s PDF has no extractable text", document_id)
        return None
    html = paragraphs_to_html(paragraphs, source=content_source.lower().replace("_", "-"))
    return html, content_source


def extract_document_id(url: str) -> int:
    item_match = ITEM_ID_RE.search(url)
    if item_match:
        return int(item_match.group(1))
    detail_match = DETAIL_ID_RE.search(url)
    if detail_match:
        return int(detail_match.group(1))
    raise FetchError("Could not extract document id from URL")


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FetchError("Only HTTP(S) URLs are supported")
    if not parsed.netloc.endswith("vbpl.vn"):
        raise FetchError("Only vbpl.vn document URLs are supported by this fetcher")


def _extract_item_id(url: str) -> int:
    match = ITEM_ID_RE.search(url)
    if not match:
        raise FetchError("VBPL URL must include ItemID")
    return int(match.group(1))


def _parse_api_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None
