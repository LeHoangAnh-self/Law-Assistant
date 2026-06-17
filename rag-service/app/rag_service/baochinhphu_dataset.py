import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

START_URL = "https://baochinhphu.vn/tra-loi-cong-dan.htm"
TIMELINE_URL = "https://baochinhphu.vn/timelinelist/102301/{page}.htm"
SOURCE_DATASET = "baochinhphu_citizen_business_answers"
SOURCE_NAME = "Báo Điện tử Chính phủ"


def clean_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


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


def parse_detail_html(
    html: str,
    url: str,
    list_metadata: dict[str, Any] | None = None,
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
    paragraphs = content_paragraphs(content_html)
    full_text = "\n".join(paragraphs)
    tags = [clean_text(tag.get_text(" ")) for tag in soup.select(".detail-tag-list a")]
    related_articles = [
        {
            "title": clean_text(item.get("data-title")),
            "url": f"https://baochinhphu.vn{item.get('data-url')}",
            "published_date": date_part(item.get("data-date")),
            "article_id": item.get("data-id"),
        }
        for item in soup.select(".kbwscwlrl[data-url]")
        if item.get("data-url")
    ]

    question_date = date_part(published_at)
    return {
        "question": build_question(title, summary),
        "title": title,
        "summary": strip_source_prefix(summary),
        "expected_answer": official_answer_from_paragraphs(paragraphs),
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
        "related_articles": related_articles,
        "image_url": image_url,
        "recommendation_text": recommendation_text(title, summary, full_text),
    }


def run_scrapy(output_path: Path, limit: int, max_pages: int, delay_seconds: float) -> None:
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

        async def start(self):
            yield scrapy.Request(START_URL, callback=self.parse_listing)
            for page in range(2, max_pages + 1):
                yield scrapy.Request(
                    TIMELINE_URL.format(page=page),
                    callback=self.parse_listing,
                    headers={"Referer": START_URL},
                )

        def parse_listing(self, response):
            for item in response.css(".box-stream-item"):
                if self.scheduled_count >= limit:
                    break
                href = item.css("a[data-linktype='newsdetail']::attr(href)").get()
                if not href:
                    continue
                url = response.urljoin(href)
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
                    meta={"list_metadata": metadata},
                )

        def parse_detail(self, response):
            if response.status >= 400:
                return
            if self.scraped_count >= limit:
                return
            self.scraped_count += 1
            yield parse_detail_html(
                response.text,
                response.url,
                response.meta.get("list_metadata"),
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    process = CrawlerProcess(
        settings={
            "FEEDS": {
                str(output_path): {
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Bảo Chính Phủ citizen/business answers for evaluation datasets."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--output", default="evaluation/baochinhphu_qa.json")
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    args = parser.parse_args()

    run_scrapy(
        output_path=Path(args.output),
        limit=args.limit,
        max_pages=args.max_pages,
        delay_seconds=args.delay_seconds,
    )
    print(f"Wrote up to {args.limit} cases to {args.output}")


if __name__ == "__main__":
    main()
