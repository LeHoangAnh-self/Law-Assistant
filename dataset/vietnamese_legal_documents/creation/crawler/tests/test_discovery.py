from law_crawler.discovery import normalize_document_url
from law_crawler.fetcher import extract_document_id


def test_normalize_current_detail_url() -> None:
    url = "https://vbpl.vn/van-ban/chi-tiet/luat-thue-thu-nhap-ca-nhan-so-109-2025-qh15--187045"

    discovered = normalize_document_url(url)

    assert discovered is not None
    assert discovered.document_id == 187045
    assert discovered.url == url


def test_normalize_legacy_fulltext_url() -> None:
    url = "https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=119147&Keyword="

    discovered = normalize_document_url(url)

    assert discovered is not None
    assert discovered.document_id == 119147


def test_ignore_non_document_url() -> None:
    assert normalize_document_url("https://vbpl.vn/van-ban/trung-uong") is None


def test_extract_document_id_from_supported_urls() -> None:
    assert extract_document_id("https://vbpl.vn/van-ban/chi-tiet/foo--123") == 123
    assert extract_document_id("https://vbpl.vn/TW/Pages/vbpq-toanvan.aspx?ItemID=456") == 456
