import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

START_URL = "https://baochinhphu.vn/tra-loi-cong-dan.htm"
TIMELINE_URL = "https://baochinhphu.vn/timelinelist/102301/{page}.htm"
SOURCE_DATASET = "baochinhphu_citizen_business_answers"
SOURCE_NAME = "Báo Điện tử Chính phủ"
DEFAULT_OUTPUT = "dataset/baochinhphu_official_qa/data_usable/rag_test_set.json"
DEFAULT_LAW_DB_PATH = "data_usable/rag/law_documents.parquet"
LEGAL_DOCUMENT_TYPES = (
    "Bộ luật",
    "Luật",
    "Nghị định",
    "Thông tư",
    "Quyết định",
    "Nghị quyết",
)
DIRECT_LEGAL_DOCUMENT_HOSTS = {"vanban.chinhphu.vn"}
DOCUMENT_NUMBER_RE = re.compile(r"\b\d{1,4}/[0-9A-ZĐa-zÀ-ỹ./-]+\b", re.IGNORECASE)

DOCUMENT_MENTION_RE = re.compile(
    r"(?P<document_type>Bộ luật|Luật|Nghị định|Thông tư|Quyết định|Nghị quyết)"
    r"(?P<document_tail>"
    r"(?:\s+(?:số\s+)?[0-9A-ZĐa-zÀ-ỹ./-]+)?"
    r"(?:\s+(?!(?:quy định|trả lời|có ý kiến|hướng dẫn|"
    r"và\s+(?:điểm|khoản|mục|điều)|"
    r"hoặc\s+(?:điểm|khoản|mục|điều))\b)"
    r"[A-ZĐÀ-Ỹa-zà-ỹ0-9()/.,-]+){0,18}"
    r")",
    re.IGNORECASE,
)
PROVISION_RE = re.compile(
    r"(?P<provision>"
    r"(?:(?:điểm|điểm)\s+[a-zđ]\d?\s*)?"
    r"(?:(?:khoản|khoản)\s+\d+[a-z]?(?:\s*,\s*khoản\s+\d+[a-z]?)*"
    r"(?:\s*(?:và|hoặc)\s*khoản\s+\d+[a-z]?)?\s*)?"
    r"(?:(?:mục|Mục)\s+[IVXLCDM\d]+(?:\s*,\s*)?)?"
    r"(?:(?:điều|Điều)\s+\d+[a-z]?)"
    r"|"
    r"(?:(?:điểm|Điểm)\s+[a-zđ]\d?\s+"
    r"(?:khoản|khoản)\s+\d+[a-z]?\s+(?:mục|Mục)\s+[IVXLCDM\d]+)"
    r"|"
    r"(?:(?:mục|Mục)\s+[IVXLCDM\d]+)"
    r")",
    re.IGNORECASE,
)


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_lookup_text(value: str | None) -> str:
    text = clean_text(value).casefold().replace("đ", "d")
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return clean_text(text)


def strip_legal_document_type(value: str | None) -> str:
    text = normalize_lookup_text(value)
    for document_type in LEGAL_DOCUMENT_TYPES:
        prefix = normalize_lookup_text(document_type)
        if text == prefix:
            return ""
        if text.startswith(f"{prefix} "):
            return text[len(prefix) + 1 :].strip()
    return text


def strip_source_prefix(value: str | None) -> str:
    text = clean_text(value)
    return re.sub(r"^\(Chinhphu\.vn\)\s*-\s*", "", text).strip()


def normalize_datetime(value: str | None) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    text = text.replace("+07:00", "+0700")
    for date_format in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%m/%d/%Y %I:%M:%S %p",
    ):
        try:
            return datetime.strptime(text, date_format).isoformat()
        except ValueError:
            continue
    return None


def date_part(value: str | None) -> str | None:
    normalized = normalize_datetime(value)
    return normalized[:10] if normalized else None


def extract_article_id(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"-(\d+)\.htm$", url)
    return match.group(1) if match else None


class LegalDocumentIndex:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.by_external_docid: dict[str, list[dict[str, Any]]] = {}
        self.by_number: dict[str, list[dict[str, Any]]] = {}
        self.by_title: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            document = {
                "document_id": row.get("document_id") or row.get("id"),
                "external_source": row.get("external_source"),
                "external_docid": row.get("external_docid"),
                "source_url": row.get("source_url"),
                "title": row.get("title"),
                "so_ky_hieu": row.get("so_ky_hieu"),
                "loai_van_ban": row.get("loai_van_ban"),
                "ngay_ban_hanh_iso": row.get("ngay_ban_hanh_iso"),
                "ngay_co_hieu_luc_iso": row.get("ngay_co_hieu_luc_iso"),
                "ngay_het_hieu_luc_iso": row.get("ngay_het_hieu_luc_iso"),
                "co_quan_ban_hanh": row.get("co_quan_ban_hanh"),
                "pham_vi": row.get("pham_vi"),
                "tinh_trang_hieu_luc": row.get("tinh_trang_hieu_luc"),
            }
            external_docid = clean_text(document["external_docid"])
            if external_docid:
                self.by_external_docid.setdefault(external_docid, []).append(document)

            number_key = normalize_lookup_text(document["so_ky_hieu"])
            if number_key:
                self.by_number.setdefault(number_key, []).append(document)

            title_key = strip_legal_document_type(document["title"])
            if title_key:
                self.by_title.setdefault(title_key, []).append(document)

    @classmethod
    def from_parquet(cls, path: Path) -> "LegalDocumentIndex":
        try:
            import pandas as pd
            import pyarrow.parquet as pq
        except ImportError as exc:
            raise RuntimeError(
                "pandas and pyarrow are required to validate legal-document links."
            ) from exc

        if not path.is_file():
            raise FileNotFoundError(f"Legal-document database not found: {path}")

        columns = [
            "title",
            "so_ky_hieu",
            "loai_van_ban",
            "ngay_ban_hanh_iso",
            "ngay_co_hieu_luc_iso",
            "ngay_het_hieu_luc_iso",
            "co_quan_ban_hanh",
            "pham_vi",
            "tinh_trang_hieu_luc",
        ]
        id_column = "document_id"
        parquet_columns = pq.ParquetFile(path).schema.names
        for optional_column in ["external_source", "external_docid", "source_url"]:
            if optional_column in parquet_columns:
                columns.append(optional_column)
        if id_column not in parquet_columns:
            id_column = "id"
        columns.insert(0, id_column)
        rows = pd.read_parquet(path, columns=columns).where(pd.notna, None).to_dict("records")
        return cls(rows)

    def match_link(self, link: dict[str, str | None]) -> list[dict[str, Any]]:
        external_docid = clean_text(link.get("external_docid"))
        if external_docid:
            matches = self.by_external_docid.get(external_docid, [])
            if matches:
                return matches

        text = link.get("text") or ""
        number_match = DOCUMENT_NUMBER_RE.search(text)
        if number_match:
            matches = self.by_number.get(normalize_lookup_text(number_match.group(0)), [])
            if matches:
                return matches

        title_key = strip_legal_document_type(text)
        if title_key:
            return self.by_title.get(title_key, [])
        return []


def matched_document_for_citation(
    citation: dict[str, str | None],
    matched_links: list[dict[str, Any]],
) -> dict[str, Any] | None:
    citation_number = normalize_lookup_text(citation.get("document_number"))
    citation_title = strip_legal_document_type(citation.get("document_name"))

    for link in matched_links:
        for document in link.get("matched_documents", []):
            document_number = normalize_lookup_text(document.get("so_ky_hieu"))
            if citation_number and citation_number == document_number:
                return document

    for link in matched_links:
        for document in link.get("matched_documents", []):
            document_title = strip_legal_document_type(document.get("title"))
            if citation_title and citation_title == document_title:
                return document

    return None


def enrich_citation_from_document(
    citation: dict[str, str | None],
    document: dict[str, Any],
) -> dict[str, Any]:
    return {
        **citation,
        "document_id": document.get("document_id"),
        "document_name": document.get("title"),
        "document_type": document.get("loai_van_ban"),
        "document_number": document.get("so_ky_hieu"),
        "document_date": document.get("ngay_ban_hanh_iso"),
        "document_status": document.get("tinh_trang_hieu_luc"),
    }


def filter_citations_to_matched_documents(
    citations: list[dict[str, str | None]],
    matched_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for citation in citations:
        document = matched_document_for_citation(citation, matched_links)
        if document:
            filtered.append(enrich_citation_from_document(citation, document))
    return filtered


def extract_direct_legal_document_links(html: str, base_url: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html or "", "html.parser")
    links: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for anchor in soup.select("a[href]"):
        href = clean_text(anchor.get("href"))
        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)
        host = parsed.netloc.casefold()
        if host not in DIRECT_LEGAL_DOCUMENT_HOSTS:
            continue
        query = parse_qs(parsed.query)
        docid = (query.get("docid") or [None])[0]
        if not docid:
            continue
        text = clean_text(anchor.get_text(" "))
        key = (absolute_url, docid)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            {
                "text": text,
                "url": absolute_url,
                "host": host,
                "external_docid": docid,
            }
        )
    return links


def extract_related_article_candidates(html: str, base_url: str) -> list[dict[str, str | None]]:
    soup = BeautifulSoup(html or "", "html.parser")
    candidates: list[dict[str, str | None]] = []
    seen_urls: set[str] = set()
    for item in soup.select(".kbwscwlrl[data-url]"):
        href = item.get("data-url")
        if not href:
            continue
        url = urljoin(base_url, href)
        if url in seen_urls:
            continue
        seen_urls.add(url)
        candidates.append(
            {
                "title": clean_text(item.get("data-title")),
                "url": url,
                "published_date": date_part(item.get("data-date")),
                "article_id": item.get("data-id"),
            }
        )
    return candidates


def content_paragraphs(html: str) -> list[str]:
    soup = BeautifulSoup(html or "", "html.parser")
    for element in soup.select(
        "script, style, .VCSortableInPreviewMode, .kbwscwl-relatedbox, figure"
    ):
        element.decompose()
    paragraphs: list[str] = []
    for paragraph in soup.find_all("p"):
        text = clean_text(paragraph.get_text(" "))
        if len(text) < 20:
            continue
        if text.casefold() in {"chinhphu.vn", "theo chinhphu.vn"}:
            continue
        paragraphs.append(text)
    return paragraphs


def official_answer_from_paragraphs(paragraphs: list[str]) -> str | None:
    if not paragraphs:
        return None

    answer_markers = (
        "trả lời vấn đề này như sau",
        "có ý kiến như sau",
        "hướng dẫn như sau",
        "trả lời như sau",
    )
    start_index = 0
    for index, paragraph in enumerate(paragraphs):
        lowered = paragraph.casefold()
        if any(marker in lowered for marker in answer_markers):
            start_index = index
            break

    return "\n".join(paragraphs[start_index:]).strip() or None


def build_question(title: str, summary: str | None) -> str:
    clean_summary = strip_source_prefix(summary)
    if clean_summary:
        return f"Tình huống: {clean_summary}\nCâu hỏi: {clean_text(title)}"
    return clean_text(title)


def recommendation_text(title: str, summary: str | None, full_text: str | None) -> str:
    parts = [clean_text(title), strip_source_prefix(summary), clean_text(full_text)]
    return "\n".join(part for part in parts if part)


def sentence_segments(text: str | None) -> list[str]:
    normalized = clean_text(text)
    if not normalized:
        return []
    return [
        segment.strip()
        for segment in re.split(r"(?<=[.!?;:])\s+(?=[A-ZĐÀ-Ỹ])|\n+", normalized)
        if segment.strip()
    ]


def normalize_document_name(document_type: str, document_tail: str | None) -> str:
    tail = clean_text(document_tail)
    tail = re.split(
        r"\s+(?:và|hoặc)\s+(?=(?:điểm|khoản|mục|điều)\b)|[,;:]\s+",
        tail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    tail = re.sub(
        r"\s+(quy định|trả lời|có ý kiến|hướng dẫn|như sau)\b.*$",
        "",
        tail,
        flags=re.IGNORECASE,
    )
    dated_document = re.match(
        r"(?P<name>.*?\bngày\s+\d{1,2}/\d{1,2}/\d{4})\b",
        tail,
        flags=re.IGNORECASE,
    )
    if dated_document:
        tail = dated_document.group("name")
    else:
        numbered_document = re.match(
            r"(?P<name>.*?(?:\bsố\s+[0-9A-ZĐa-zÀ-ỹ./-]+|\b[0-9]{1,4}/[0-9A-ZĐa-zÀ-ỹ./-]+))\b",
            tail,
            flags=re.IGNORECASE,
        )
        if numbered_document:
            tail = numbered_document.group("name")
    tail = tail.strip(" ,.;:")
    return clean_text(f"{document_type} {tail}")


def extract_document_number(document_name: str) -> str | None:
    match = re.search(
        r"\bsố\s+([0-9A-ZĐa-zÀ-ỹ./-]+)|\b([0-9]{1,4}/[0-9A-ZĐa-zÀ-ỹ./-]+)",
        document_name,
        flags=re.IGNORECASE,
    )
    return next((group for group in match.groups() if group), None) if match else None


def extract_document_date(document_name: str) -> str | None:
    match = re.search(
        r"\bngày\s+(\d{1,2}/\d{1,2}/\d{4})|\bnăm\s+(\d{4})",
        document_name,
        flags=re.IGNORECASE,
    )
    return next((group for group in match.groups() if group), None) if match else None


def nearest_provision_before(segment: str, document_start: int) -> str | None:
    prefix = segment[max(0, document_start - 180) : document_start]
    matches = list(PROVISION_RE.finditer(prefix))
    if not matches:
        return None
    return clean_text(matches[-1].group("provision"))


def extract_legal_citations(text: str | None) -> list[dict[str, str | None]]:
    citations: list[dict[str, str | None]] = []
    seen: set[tuple[str | None, str, str | None]] = set()

    for segment in sentence_segments(text):
        for match in DOCUMENT_MENTION_RE.finditer(segment):
            document_name = normalize_document_name(
                match.group("document_type"),
                match.group("document_tail"),
            )
            if document_name.casefold() in {item.casefold() for item in LEGAL_DOCUMENT_TYPES}:
                continue

            provision = nearest_provision_before(segment, match.start())
            citation_text_start = match.start()
            if provision:
                provision_match = list(PROVISION_RE.finditer(segment[: match.start()]))
                if provision_match:
                    citation_text_start = provision_match[-1].start()
            citation_text = clean_text(segment[citation_text_start : match.end()])
            key = (
                provision.casefold() if provision else None,
                document_name.casefold(),
                citation_text,
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "provision": provision,
                    "document_name": document_name,
                    "document_type": match.group("document_type"),
                    "document_number": extract_document_number(document_name),
                    "document_date": extract_document_date(document_name),
                    "citation_text": citation_text,
                }
            )

    return citations


def parse_detail_html(
    html: str,
    url: str,
    list_metadata: dict[str, Any] | None = None,
    legal_document_index: LegalDocumentIndex | None = None,
) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    list_metadata = list_metadata or {}

    title = clean_text(
        soup.select_one(".detail-title").get_text(" ")
        if soup.select_one(".detail-title")
        else soup.find("title").get_text(" ")
        if soup.find("title")
        else list_metadata.get("title")
    )
    summary = clean_text(
        soup.select_one(".detail-sapo").get_text(" ")
        if soup.select_one(".detail-sapo")
        else list_metadata.get("summary")
    )
    category = clean_text(
        soup.select_one("[data-role='cate-name']").get_text(" ")
        if soup.select_one("[data-role='cate-name']")
        else list_metadata.get("category")
    )
    published_at = (
        soup.find("meta", property="article:published_time") or {}
    ).get("content") or list_metadata.get("published_at")
    modified_at = (soup.find("meta", property="article:modified_time") or {}).get("content")
    image_url = (soup.find("meta", property="og:image") or {}).get("content")

    content_html = str(soup.select_one(".detail-content") or "")
    direct_legal_document_links = extract_direct_legal_document_links(content_html, url)
    matched_direct_legal_documents: list[dict[str, Any]] = []
    for link in direct_legal_document_links:
        matches = legal_document_index.match_link(link) if legal_document_index else []
        if matches:
            matched_direct_legal_documents.append({**link, "matched_documents": matches})

    paragraphs = content_paragraphs(content_html)
    full_text = "\n".join(paragraphs)
    expected_answer = official_answer_from_paragraphs(paragraphs)
    extracted_legal_citations = extract_legal_citations(expected_answer or full_text)
    legal_citations = filter_citations_to_matched_documents(
        extracted_legal_citations,
        matched_direct_legal_documents,
    )
    tags = [clean_text(tag.get_text(" ")) for tag in soup.select(".detail-tag-list a")]

    question_date = date_part(published_at)
    return {
        "question": build_question(title, summary),
        "title": title,
        "summary": strip_source_prefix(summary),
        "expected_answer": expected_answer,
        "expected_legal_citations": legal_citations,
        "expected_citation_text": "\n".join(
            citation["citation_text"] or "" for citation in legal_citations
        ),
        "full_text": full_text,
        "source_url": url,
        "source_name": SOURCE_NAME,
        "source_dataset": SOURCE_DATASET,
        "answer_type": "official_reference",
        "category": category,
        "published_at": normalize_datetime(published_at),
        "published_date": question_date,
        "modified_at": normalize_datetime(modified_at),
        "question_date": question_date,
        "retrieval_cutoff_date": question_date,
        "article_id": extract_article_id(url),
        "tags": tags,
        "image_url": image_url,
        "direct_legal_document_links": [
            {key: value for key, value in link.items() if key != "matched_documents"}
            for link in matched_direct_legal_documents
        ],
        "matched_direct_legal_documents": matched_direct_legal_documents,
        "direct_legal_document_link_count": len(matched_direct_legal_documents),
        "matched_direct_legal_document_count": len(matched_direct_legal_documents),
        "recommendation_text": recommendation_text(title, summary, full_text),
    }


def listing_page_urls(max_pages: int, newest_first: bool = True) -> list[str]:
    if max_pages < 1:
        return []
    urls = [START_URL]
    urls.extend(TIMELINE_URL.format(page=page) for page in range(2, max_pages + 1))
    return urls if newest_first else list(reversed(urls))


def load_existing_items(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.is_file():
        return []
    text = output_path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list in existing dataset: {output_path}")
    return [item for item in data if isinstance(item, dict)]


def item_identity(item: dict[str, Any]) -> str | None:
    source_url = item.get("source_url")
    if source_url:
        return str(source_url)
    article_id = item.get("article_id")
    return str(article_id) if article_id else None


def merge_items(
    existing_items: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in [*existing_items, *new_items]:
        identity = item_identity(item)
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        merged.append(item)
    return merged


def write_json_dataset(output_path: Path, items: list[dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def run_scrapy(
    output_path: Path,
    limit: int,
    max_pages: int,
    delay_seconds: float,
    legal_document_index: LegalDocumentIndex | None = None,
    require_all_linked_documents: bool = False,
    newest_first: bool = True,
    related_depth: int = 1,
) -> None:
    existing_items = load_existing_items(output_path)
    existing_urls = {item_identity(item) for item in existing_items if item_identity(item)}
    remaining_capacity = max(0, limit - len(existing_items))
    if remaining_capacity <= 0:
        print(
            f"Dataset already has {len(existing_items)} items, meeting target limit {limit}."
        )
        return

    try:
        import scrapy
        from scrapy.crawler import CrawlerProcess
    except ImportError as exc:
        raise RuntimeError(
            "Scrapy is required. Install the dev environment or add scrapy."
        ) from exc

    class BaoChinhPhuSpider(scrapy.Spider):
        name = "baochinhphu_citizen_answers"
        custom_settings = {
            "USER_AGENT": (
                "Mozilla/5.0 (compatible; LawAssistantDatasetBot/0.1; "
                "+https://localhost)"
            ),
            "DOWNLOAD_DELAY": delay_seconds,
            "CONCURRENT_REQUESTS": 1,
            "ROBOTSTXT_OBEY": True,
            "LOG_LEVEL": "INFO",
        }

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.scheduled_count = 0
            self.scraped_count = 0
            self.accepted_count = 0
            self.scheduled_urls = set(existing_urls)

        async def start(self):
            if remaining_capacity <= 0:
                return
            for url in listing_page_urls(max_pages=max_pages, newest_first=newest_first):
                headers = {"Referer": START_URL} if url != START_URL else None
                yield scrapy.Request(
                    url,
                    callback=self.parse_listing,
                    headers=headers,
                )

        def parse_listing(self, response):
            for item in response.css(".box-stream-item"):
                if self.accepted_count >= remaining_capacity:
                    break
                href = item.css("a[data-linktype='newsdetail']::attr(href)").get()
                if not href:
                    continue
                url = response.urljoin(href)
                if url in self.scheduled_urls:
                    continue
                self.scheduled_urls.add(url)
                metadata = {
                    "title": item.css("a[data-linktype='newsdetail']::text").get(),
                    "summary": item.css(".box-stream-sapo::text").get(),
                    "category": item.css(".box-stream-category::text").get(),
                    "published_at": item.css(".box-stream-time::text").get(),
                }
                self.scheduled_count += 1
                yield scrapy.Request(
                    url,
                    callback=self.parse_detail,
                    meta={"list_metadata": metadata, "related_depth": 0},
                )

        def parse_detail(self, response):
            if response.status >= 400:
                return
            if self.accepted_count >= remaining_capacity:
                return
            self.scraped_count += 1
            current_related_depth = int(response.meta.get("related_depth", 0))
            if current_related_depth < related_depth:
                for candidate in extract_related_article_candidates(response.text, response.url):
                    candidate_url = candidate.get("url")
                    if not candidate_url or candidate_url in self.scheduled_urls:
                        continue
                    self.scheduled_urls.add(candidate_url)
                    yield scrapy.Request(
                        candidate_url,
                        callback=self.parse_detail,
                        meta={
                            "list_metadata": {
                                "title": candidate.get("title"),
                                "published_at": candidate.get("published_date"),
                            },
                            "related_depth": current_related_depth + 1,
                        },
                    )
            item = parse_detail_html(
                response.text,
                response.url,
                response.meta.get("list_metadata"),
                legal_document_index=legal_document_index,
            )
            if not item["direct_legal_document_links"]:
                self.logger.info("Skipping %s: no direct legal-document links", response.url)
                return
            if not item["matched_direct_legal_documents"]:
                self.logger.info(
                    "Skipping %s: direct legal-document links are not in local DB",
                    response.url,
                )
                return
            raw_direct_link_count = len(
                extract_direct_legal_document_links(response.text, response.url)
            )
            if require_all_linked_documents and (
                item["matched_direct_legal_document_count"] != raw_direct_link_count
            ):
                self.logger.info(
                    "Skipping %s: not all direct legal-document links are in local DB",
                    response.url,
                )
                return
            self.accepted_count += 1
            yield item

    new_output_path = output_path.with_name(f"{output_path.stem}.new{output_path.suffix}")
    if new_output_path.exists():
        new_output_path.unlink()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    process = CrawlerProcess(
        settings={
            "FEEDS": {
                str(new_output_path): {
                    "format": "json",
                    "encoding": "utf8",
                    "indent": 2,
                    "overwrite": True,
                }
            }
        }
    )
    process.crawl(BaoChinhPhuSpider)
    process.start()
    new_items = load_existing_items(new_output_path)
    merged_items = merge_items(existing_items, new_items)
    write_json_dataset(output_path, merged_items[:limit])
    if new_output_path.exists():
        new_output_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Bảo Chính Phủ citizen/business answers for evaluation datasets."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--law-db-path", default=DEFAULT_LAW_DB_PATH)
    parser.add_argument(
        "--related-depth",
        type=int,
        default=1,
        help="Depth for discovering additional candidates from related-article links.",
    )
    parser.add_argument(
        "--oldest-first",
        action="store_true",
        help="Scan listing pages from older to newer instead of the default newer-to-older order.",
    )
    parser.add_argument(
        "--require-all-linked-documents",
        action="store_true",
        help="Only keep pages when every direct legal-document link matches the local DB.",
    )
    args = parser.parse_args()
    legal_document_index = LegalDocumentIndex.from_parquet(Path(args.law_db_path))

    run_scrapy(
        output_path=Path(args.output),
        limit=args.limit,
        max_pages=args.max_pages,
        delay_seconds=args.delay_seconds,
        legal_document_index=legal_document_index,
        require_all_linked_documents=args.require_all_linked_documents,
        newest_first=not args.oldest_first,
        related_depth=args.related_depth,
    )
    print(f"Dataset target size is {args.limit} items at {args.output}")


if __name__ == "__main__":
    main()
