from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests

from law_crawler.config import Settings
from law_crawler.fetcher import extract_document_id


LOGGER = logging.getLogger(__name__)
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DETAIL_URL_RE = re.compile(r"/van-ban/chi-tiet/.+--\d+(?:[/?#]|$)")
LEGACY_FULLTEXT_RE = re.compile(r"/Pages/vbpq-toanvan\.aspx\?[^#]*ItemID=\d+", re.IGNORECASE)


@dataclass(frozen=True)
class DiscoveredUrl:
    url: str
    document_id: int


def discover_from_sitemap(
    sitemap_url: str,
    settings: Settings,
    *,
    limit: int | None = None,
    on_discovered: Callable[[DiscoveredUrl], None] | None = None,
    progress_every: int = 5000,
) -> list[DiscoveredUrl]:
    seen_sitemaps: set[str] = set()
    seen_docs: dict[int, DiscoveredUrl] = {}

    def visit(url: str) -> None:
        if limit is not None and len(seen_docs) >= limit:
            return
        if url in seen_sitemaps:
            return
        seen_sitemaps.add(url)
        LOGGER.info("Reading sitemap %s", url)
        response = requests.get(
            url,
            headers={"User-Agent": settings.user_agent, "Accept": "application/xml,text/xml,*/*"},
            timeout=settings.timeout_seconds,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        tag = _strip_ns(root.tag)

        if tag == "sitemapindex":
            for loc in root.findall("sm:sitemap/sm:loc", SITEMAP_NS):
                if loc.text:
                    visit(urljoin(url, loc.text.strip()))
            return

        if tag != "urlset":
            LOGGER.warning("Ignoring unknown sitemap root=%s url=%s", tag, url)
            return

        for loc in root.findall("sm:url/sm:loc", SITEMAP_NS):
            if limit is not None and len(seen_docs) >= limit:
                return
            if not loc.text:
                continue
            discovered = normalize_document_url(loc.text.strip())
            if discovered:
                if discovered.document_id not in seen_docs:
                    seen_docs[discovered.document_id] = discovered
                    if on_discovered:
                        on_discovered(discovered)
                    if progress_every > 0 and len(seen_docs) % progress_every == 0:
                        LOGGER.info("Discovered %s document URLs so far", len(seen_docs))

    visit(sitemap_url)
    LOGGER.info("Finished discovery: sitemaps=%s documents=%s", len(seen_sitemaps), len(seen_docs))
    return list(seen_docs.values())


def discover_from_seed_file(path: str) -> list[DiscoveredUrl]:
    with open(path, "r", encoding="utf-8") as seed_file:
        return [url for url in (normalize_document_url(line.strip()) for line in seed_file) if url]


def normalize_document_url(url: str) -> DiscoveredUrl | None:
    if not url or url.startswith("#"):
        return None
    if DETAIL_URL_RE.search(url) or LEGACY_FULLTEXT_RE.search(url):
        return DiscoveredUrl(url=url, document_id=extract_document_id(url))
    return None


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
