from __future__ import annotations

from types import SimpleNamespace

import pytest
import requests

from law_crawler.fetcher import (
    FetchError,
    _best_google_thuvienphapluat_result,
    _best_thuvienphapluat_search_result,
    _load_cookie_header,
    _thuvienphapluat_query_from_source_url,
    fetch_vbpl_document_by_id,
)


class FakeResponse:
    def __init__(self, *, status_code: int = 200, content: bytes = b"", payload: dict | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error

    def json(self) -> dict:
        return self._payload


def test_vbpl_api_400_falls_back_to_thuvienphapluat(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fallback_map = tmp_path / "fallback.csv"
    fallback_map.write_text(
        "document_id,url\n"
        "160483,https://thuvienphapluat.vn/van-ban/Doanh-nghiep/example-564268.aspx\n",
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        user_agent="test-agent",
        timeout_seconds=5,
        vbpl_api_base_url="https://vbpl-bientap-gateway.moj.gov.vn/api",
        thuvienphapluat_fallback_map_file=str(fallback_map),
        thuvienphapluat_cookie_file=None,
    )
    calls: list[str] = []

    def fake_get(url: str, **kwargs) -> FakeResponse:
        calls.append(url)
        if "vbpl-bientap-gateway" in url:
            return FakeResponse(status_code=400)
        return FakeResponse(
            content="""
            <html>
              <head><meta property="og:title" content="Quyet dinh 09/2023/QD-UBND"></head>
              <body>
                <div id="divContentDoc">
                  <p>QUYET DINH</p>
                  <p>Điều 1. Phạm vi điều chỉnh</p>
                  <p>1. Nội dung cần crawl.</p>
                </div>
              </body>
            </html>
            """.encode("utf-8"),
        )

    monkeypatch.setattr("law_crawler.fetcher.requests.get", fake_get)

    fetched = fetch_vbpl_document_by_id(160483, "https://vbpl.vn/broken--160483", settings)

    assert calls == [
        "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/160483",
        "https://thuvienphapluat.vn/van-ban/Doanh-nghiep/example-564268.aspx",
    ]
    assert fetched.document_id == 160483
    assert fetched.source_url == "https://vbpl.vn/broken--160483"
    assert fetched.content_source == "TVPL_HTML"
    assert "Nội dung cần crawl" in fetched.html
    assert fetched.title == "Quyet dinh 09/2023/QD-UBND"


def test_thuvienphapluat_fallback_rejects_untrusted_domains(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    fallback_map = tmp_path / "fallback.csv"
    fallback_map.write_text("document_id,url\n160483,https://example.com/doc\n", encoding="utf-8")
    settings = SimpleNamespace(
        user_agent="test-agent",
        timeout_seconds=5,
        vbpl_api_base_url="https://vbpl-bientap-gateway.moj.gov.vn/api",
        thuvienphapluat_fallback_map_file=str(fallback_map),
        thuvienphapluat_cookie_file=None,
    )

    monkeypatch.setattr("law_crawler.fetcher.requests.get", lambda *args, **kwargs: FakeResponse(status_code=400))

    with pytest.raises(FetchError, match="thuvienphapluat.vn"):
        fetch_vbpl_document_by_id(160483, "https://vbpl.vn/broken--160483", settings)


def test_vbpl_api_400_auto_searches_thuvienphapluat_when_no_map(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        user_agent="test-agent",
        timeout_seconds=5,
        vbpl_api_base_url="https://vbpl-bientap-gateway.moj.gov.vn/api",
        thuvienphapluat_fallback_map_file=None,
        thuvienphapluat_cookie_file=None,
    )
    source_url = (
        "https://vbpl.vn/van-ban/chi-tiet/quyet-dinh-so-48-2022-qd-ubnd-quy-dinh-nguyen-tac-tieu-chi-"
        "dinh-muc-phan-bo-nguon-ngan-sach-trung-uong-va-ty-le-von-doi-ung-cua-ngan-sach-dia-phuong-"
        "thuc-hien-chuong-trinh-muc-tieu-quoc-gia-xay-dung-nong-thon-moi-tinh-binh-dinh-giai-doan-"
        "2021-2025--155366"
    )
    calls: list[str] = []

    def fake_get(url: str, **kwargs) -> FakeResponse:
        calls.append(url)
        if "vbpl-bientap-gateway" in url:
            return FakeResponse(status_code=400)
        if "google.com/search" in url:
            return FakeResponse(
                content="""
                <html><body>
                  <a href="/url?q=https://thuvienphapluat.vn/van-ban/Tai-chinh-nha-nuoc/Quyet-dinh-48-2022-QD-UBND-dinh-muc-phan-bo-nguon-ngan-sach-xay-dung-nong-thon-moi-Binh-Dinh-525758.aspx&sa=U">
                    Quyết định 48/2022/QĐ-UBND định mức phân bổ nguồn ngân sách xây dựng nông thôn mới Bình Định
                  </a>
                </body></html>
                """.encode("utf-8"),
            )
        if "tim-van-ban.aspx" in url:
            return FakeResponse(
                content="""
                <html><body>
                  <a href="/van-ban/Tai-chinh-nha-nuoc/Quyet-dinh-48-2022-QD-UBND-dinh-muc-phan-bo-nguon-ngan-sach-xay-dung-nong-thon-moi-Binh-Dinh-525758.aspx">
                    Quyết định 48/2022/QĐ-UBND định mức phân bổ nguồn ngân sách xây dựng nông thôn mới Bình Định
                  </a>
                </body></html>
                """.encode("utf-8"),
            )
        return FakeResponse(
            content="""
            <html><body>
              <h1>Quyết định 48/2022/QĐ-UBND</h1>
              <div id="divContentDoc">
                <p>QUYẾT ĐỊNH</p>
                <p>Điều 1. Phạm vi điều chỉnh</p>
                <p>1. Nội dung fallback tự động.</p>
              </div>
            </body></html>
            """.encode("utf-8"),
        )

    monkeypatch.setattr("law_crawler.fetcher.requests.get", fake_get)

    fetched = fetch_vbpl_document_by_id(155366, source_url, settings)

    assert calls[0] == "https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public/doc/155366"
    assert "google.com/search" in calls[1]
    assert "site%3Athuvienphapluat.vn%2Fvan-ban" in calls[1]
    assert "quyet-dinh-so-48-2022-qd-ubnd" in calls[1]
    assert calls[2] == (
        "https://thuvienphapluat.vn/van-ban/Tai-chinh-nha-nuoc/"
        "Quyet-dinh-48-2022-QD-UBND-dinh-muc-phan-bo-nguon-ngan-sach-xay-dung-nong-thon-moi-Binh-Dinh-525758.aspx"
    )
    assert fetched.document_id == 155366
    assert fetched.content_source == "TVPL_HTML"
    assert "Nội dung fallback tự động" in fetched.html


def test_thuvienphapluat_query_uses_full_vbpl_slug() -> None:
    source_url = (
        "https://vbpl.vn/van-ban/chi-tiet/nghi-quyet-so-90-2018-nq-hdnd-quy-dinh-noi-dung-muc-chi-"
        "cho-cong-tac-quan-ly-nha-nuoc-ve-thi-hanh-phap-luat-xu-ly-vi-pham-hanh-chinh-tren-dia-ban-"
        "tinh-gia-lai--129952"
    )

    assert _thuvienphapluat_query_from_source_url(source_url) == (
        "nghi-quyet-so-90-2018-nq-hdnd-quy-dinh-noi-dung-muc-chi-cho-cong-tac-quan-ly-nha-nuoc-ve-"
        "thi-hanh-phap-luat-xu-ly-vi-pham-hanh-chinh-tren-dia-ban-tinh-gia-lai"
    )


def test_best_google_thuvienphapluat_result_scores_matching_legal_doc() -> None:
    source_url = (
        "https://vbpl.vn/van-ban/chi-tiet/nghi-quyet-so-90-2018-nq-hdnd-quy-dinh-noi-dung-muc-chi-"
        "cho-cong-tac-quan-ly-nha-nuoc-ve-thi-hanh-phap-luat-xu-ly-vi-pham-hanh-chinh-tren-dia-ban-"
        "tinh-gia-lai--129952"
    )
    html = """
    <html><body>
      <a href="/url?q=https://example.com/not-tvpl.aspx&sa=U">Wrong domain</a>
      <a href="/url?q=https://thuvienphapluat.vn/tin-tuc/not-a-doc.aspx&sa=U">Not document</a>
      <a href="/url?q=https://thuvienphapluat.vn/van-ban/Vi-pham-hanh-chinh/Nghi-quyet-90-2018-NQ-HDND-quan-ly-nha-nuoc-thi-hanh-phap-luat-xu-ly-vi-pham-hanh-chinh-Gia-Lai-401234.aspx&sa=U">
        Nghị quyết 90/2018/NQ-HĐND quản lý nhà nước về thi hành pháp luật xử lý vi phạm hành chính Gia Lai
      </a>
    </body></html>
    """.encode("utf-8")

    assert _best_google_thuvienphapluat_result(html, source_url) == (
        "https://thuvienphapluat.vn/van-ban/Vi-pham-hanh-chinh/"
        "Nghi-quyet-90-2018-NQ-HDND-quan-ly-nha-nuoc-thi-hanh-phap-luat-xu-ly-vi-pham-hanh-chinh-Gia-Lai-401234.aspx"
    )


def test_best_thuvienphapluat_search_result_scores_matching_legal_doc() -> None:
    source_url = (
        "https://vbpl.vn/van-ban/chi-tiet/quyet-dinh-so-48-2022-qd-ubnd-quy-dinh-nguyen-tac-tieu-chi-"
        "dinh-muc-phan-bo-nguon-ngan-sach-trung-uong--155366"
    )
    html = """
    <html><body>
      <a href="/tin-tuc/not-a-doc.aspx">Tin tức không phải văn bản</a>
      <a href="/van-ban/Doanh-nghiep/Quyet-dinh-99-2022-QD-UBND-khac-111.aspx">Quyết định khác</a>
      <a href="/van-ban/Tai-chinh-nha-nuoc/Quyet-dinh-48-2022-QD-UBND-dinh-muc-phan-bo-nguon-ngan-sach-Binh-Dinh-525758.aspx">
        Quyết định 48/2022/QĐ-UBND định mức phân bổ nguồn ngân sách Bình Định
      </a>
    </body></html>
    """.encode("utf-8")

    assert _best_thuvienphapluat_search_result(html, source_url) == (
        "https://thuvienphapluat.vn/van-ban/Tai-chinh-nha-nuoc/"
        "Quyet-dinh-48-2022-QD-UBND-dinh-muc-phan-bo-nguon-ngan-sach-Binh-Dinh-525758.aspx"
    )


def test_load_cookie_header_supports_netscape_cookie_file(tmp_path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".thuvienphapluat.vn\tTRUE\t/\tTRUE\t1999999999\tSESSION_ID\tabc123\n",
        encoding="utf-8",
    )

    assert _load_cookie_header(str(cookie_file)) == "SESSION_ID=abc123"
