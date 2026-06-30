from __future__ import annotations

import argparse
import csv
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

from law_crawler.config import Settings, load_settings
from law_crawler.db import create_db_engine
from law_crawler.fetcher import (
    TVPL_DOCUMENT_RE,
    TVPL_STOPWORDS,
    FetchedDocument,
    _extract_document_number_tokens,
    _extract_thuvienphapluat_content,
    _extract_thuvienphapluat_title,
    _lookup_thuvienphapluat_fallback_url,
    _normalized_tokens,
    _thuvienphapluat_headers,
    _thuvienphapluat_query_from_source_url,
)
from law_crawler.parser import parse_document_html


SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


@dataclass(frozen=True)
class FailedJob:
    document_id: int
    source_url: str
    last_error: str


@dataclass(frozen=True)
class VerifiedFallback:
    document_id: int
    source_url: str
    query: str
    fallback_url: str
    title: str
    html_len: int
    articles: int
    tables: int
    score: float
    search_engine: str


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--delay-seconds", type=float, default=0.7)
    parser.add_argument("--report", default="data_usable/review/resolved_tvpl_fallbacks.csv")
    parser.add_argument("--map-file", default="data_usable/thuvienphapluat_fallback_urls.csv")
    args = parser.parse_args()

    settings = load_settings()
    map_path = Path(args.map_file)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_existing_map(map_path)
    jobs = failed_vbpl_400_jobs(args.limit, settings)
    verified: list[VerifiedFallback] = []
    report_rows: list[dict[str, str | int | float]] = []

    for index, job in enumerate(jobs, start=1):
        query = _thuvienphapluat_query_from_source_url(job.source_url) or ""
        if not query:
            report_rows.append(report_row(job, "", "missing_query"))
            continue
        if job.document_id in existing:
            report_rows.append(report_row(job, query, "already_mapped", fallback_url=existing[job.document_id]))
            continue

        print(f"[{index}/{len(jobs)}] searching document_id={job.document_id} query={query[:90]}", flush=True)
        candidate = resolve_candidate(job.source_url, query)
        if candidate is None:
            report_rows.append(report_row(job, query, "not_found"))
            time.sleep(args.delay_seconds)
            continue

        fallback_url, score, engine = candidate
        verified_item = verify_candidate(settings, job, query, fallback_url, score, engine)
        if verified_item is None:
            report_rows.append(report_row(job, query, "candidate_not_crawlable", fallback_url=fallback_url))
            time.sleep(args.delay_seconds)
            continue

        verified.append(verified_item)
        existing[job.document_id] = verified_item.fallback_url
        report_rows.append(
            report_row(
                job,
                query,
                "verified",
                fallback_url=verified_item.fallback_url,
                title=verified_item.title,
                articles=verified_item.articles,
                tables=verified_item.tables,
                score=verified_item.score,
                search_engine=verified_item.search_engine,
            )
        )
        append_mapping(map_path, verified_item.document_id, verified_item.fallback_url)
        print(
            f"  verified {verified_item.fallback_url} "
            f"articles={verified_item.articles} tables={verified_item.tables}",
            flush=True,
        )
        time.sleep(args.delay_seconds)

    write_report(report_path, report_rows)
    print(f"jobs={len(jobs)} verified={len(verified)} report={report_path}")
    print(f"map_file={map_path}")
    return 0


def failed_vbpl_400_jobs(limit: int | None, settings: Settings) -> list[FailedJob]:
    engine = create_db_engine(settings)
    sql = """
            select document_id, source_url, last_error
            from crawl_jobs
            where status = 'FAILED'
              and last_error like '%400 Client Error: Bad Request%'
            order by updated_at, id
        """
    params = {}
    if limit:
        sql += " limit :limit"
        params["limit"] = int(limit)

    with engine.connect() as connection:
        rows = connection.execute(text(sql), params).mappings()
        return [
            FailedJob(
                document_id=int(row["document_id"]),
                source_url=str(row["source_url"] or ""),
                last_error=str(row["last_error"] or ""),
            )
            for row in rows
        ]


def resolve_candidate(source_url: str, query: str) -> tuple[str, float, str] | None:
    search_query = f"site:thuvienphapluat.vn/van-ban {query}"
    candidates: dict[str, tuple[str, str]] = {}
    for engine, search_url in search_urls(search_query):
        try:
            response = requests.get(search_url, headers=SEARCH_HEADERS, timeout=20)
            response.raise_for_status()
        except requests.RequestException:
            continue
        for url, text in extract_search_candidates(response.text, engine):
            candidates.setdefault(url, (text, engine))
        if candidates:
            break

    if not candidates:
        return None

    scored = [
        (strict_title_score(source_url, candidate_url, text), candidate_url, engine)
        for candidate_url, (text, engine) in candidates.items()
        if candidate_matches_document_number(source_url, candidate_url, text)
    ]
    if not scored:
        return None
    score, url, engine = max(scored, key=lambda item: item[0])
    if score < 0.5:
        return None
    return url, score, engine


def strict_title_score(source_url: str, candidate_url: str, candidate_text: str) -> float:
    source_tokens = distinctive_tokens(source_url)
    candidate_tokens = distinctive_tokens(f"{candidate_url} {candidate_text}")
    if not source_tokens or not candidate_tokens:
        return 0.0
    return len(source_tokens & candidate_tokens) / len(source_tokens)


def distinctive_tokens(value: str) -> set[str]:
    doc_number_tokens = set(_extract_document_number_tokens(_normalized_tokens(value)))
    return {
        token
        for token in _normalized_tokens(value)
        if token not in TVPL_STOPWORDS and token not in doc_number_tokens and len(token) > 1
    }


def candidate_matches_document_number(source_url: str, candidate_url: str, candidate_text: str) -> bool:
    source_doc_number = _extract_document_number_tokens(_normalized_tokens(source_url))
    if not source_doc_number:
        return True
    candidate_tokens = set(_normalized_tokens(f"{candidate_url} {candidate_text}"))
    return all(token in candidate_tokens for token in source_doc_number[:2])


def search_urls(search_query: str) -> list[tuple[str, str]]:
    encoded = quote_plus(search_query)
    return [
        ("google", f"https://www.google.com/search?q={encoded}"),
        ("brave", f"https://search.brave.com/search?q={encoded}"),
        ("duckduckgo", f"https://duckduckgo.com/html/?q={encoded}"),
        ("bing", f"https://www.bing.com/search?q={encoded}"),
    ]


def extract_search_candidates(html: str, engine: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[tuple[str, str]] = []
    for link in soup.find_all("a", href=True):
        href = str(link["href"])
        url = normalize_search_href(href)
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.hostname not in {"thuvienphapluat.vn", "www.thuvienphapluat.vn"}:
            continue
        if not TVPL_DOCUMENT_RE.search(parsed.path):
            continue
        text = " ".join(link.get_text(" ", strip=True).split())
        candidates.append((url, text or engine))
    return candidates


def normalize_search_href(href: str) -> str | None:
    if href.startswith("/url?"):
        values = parse_qs(urlparse(href).query).get("q")
        return values[0] if values else None
    if "duckduckgo.com/l/?" in href:
        values = parse_qs(urlparse(href).query).get("uddg")
        return unquote(values[0]) if values else None
    if href.startswith("//"):
        href = "https:" + href
    if href.startswith("https://thuvienphapluat.vn/") or href.startswith("https://www.thuvienphapluat.vn/"):
        return href
    return None


def verify_candidate(
    settings,
    job: FailedJob,
    query: str,
    fallback_url: str,
    score: float,
    engine: str,
) -> VerifiedFallback | None:
    try:
        fetched = fetch_direct_thuvienphapluat_document(settings, job.document_id, fallback_url)
        parsed = parse_document_html(fetched.html)
    except Exception:
        return None
    if not fetched.html.strip():
        return None
    return VerifiedFallback(
        document_id=job.document_id,
        source_url=job.source_url,
        query=query,
        fallback_url=fallback_url,
        title=fetched.title or "",
        html_len=len(fetched.html),
        articles=len(parsed.articles),
        tables=len(parsed.tables),
        score=round(score, 4),
        search_engine=engine,
    )


def fetch_direct_thuvienphapluat_document(settings, document_id: int, fallback_url: str) -> FetchedDocument:
    response = requests.get(
        fallback_url,
        headers=_thuvienphapluat_headers(settings, referer="https://www.google.com/"),
        timeout=settings.timeout_seconds,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    content = _extract_thuvienphapluat_content(soup)
    if content is None:
        raise RuntimeError("TVPL content container not found")
    return FetchedDocument(
        document_id=document_id,
        source_url=fallback_url,
        html=str(content),
        content_source="TVPL_HTML",
        title=_extract_thuvienphapluat_title(soup),
    )


def load_existing_map(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        return {
            int(row["document_id"]): row["url"].strip()
            for row in rows
            if row.get("document_id") and row.get("url")
        }


def append_mapping(path: Path, document_id: int, fallback_url: str) -> None:
    needs_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if needs_header:
            writer.writerow(["document_id", "url"])
        writer.writerow([document_id, fallback_url])


def report_row(
    job: FailedJob,
    query: str,
    status: str,
    *,
    fallback_url: str = "",
    title: str = "",
    articles: int | str = "",
    tables: int | str = "",
    score: float | str = "",
    search_engine: str = "",
) -> dict[str, str | int | float]:
    return {
        "document_id": job.document_id,
        "status": status,
        "query": query,
        "fallback_url": fallback_url,
        "title": title,
        "articles": articles,
        "tables": tables,
        "score": score,
        "search_engine": search_engine,
        "source_url": job.source_url,
        "last_error": job.last_error.replace("\r", " ").replace("\n", " "),
    }


def write_report(path: Path, rows: list[dict[str, str | int | float]]) -> None:
    fieldnames = [
        "document_id",
        "status",
        "query",
        "fallback_url",
        "title",
        "articles",
        "tables",
        "score",
        "search_engine",
        "source_url",
        "last_error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
