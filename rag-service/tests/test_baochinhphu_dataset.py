import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_CREATION_DIR = PROJECT_ROOT / "dataset" / "baochinhphu_official_qa" / "creation"
sys.path.insert(0, str(DATASET_CREATION_DIR))

from baochinhphu_dataset import (  # noqa: E402
    LegalDocumentIndex,
    extract_direct_legal_document_links,
    extract_legal_citations,
    extract_related_article_candidates,
    listing_page_urls,
    load_existing_items,
    merge_items,
    parse_detail_html,
    write_json_dataset,
)


def test_parse_detail_html_builds_eval_and_recommendation_fields() -> None:
    html = """
    <html>
      <head>
        <meta property="article:published_time" content="2026-06-17T15:07:00+07:00" />
        <meta property="article:modified_time" content="2026-06-17T17:45:00+07:00" />
        <meta property="og:image" content="https://example.test/image.jpg" />
      </head>
      <body>
        <a data-role="cate-name">Trả lời công dân - doanh nghiệp</a>
        <h1 class="detail-title">Xác định hạn mức đất ở</h1>
        <h2 class="detail-sapo">(Chinhphu.vn) - Ông A hỏi về hạn mức đất ở.</h2>
        <div class="detail-content">
          <p>Ông A hỏi, trường hợp của ông áp dụng hạn mức nào?</p>
          <p><i>Bộ Nông nghiệp và Môi trường trả lời vấn đề này như sau:</i></p>
          <p>Việc xác định hạn mức đất ở thực hiện theo Luật Đất đai năm 2024.</p>
          <p style="text-align: right;"><b>Chinhphu.vn</b></p>
          <div class="VCSortableInPreviewMode"><p>Không lấy tin liên quan.</p></div>
        </div>
        <ul class="detail-tag-list"><li><a>đất đai</a></li></ul>
        <li class="kbwscwlrl" data-title="Tin liên quan" data-url="/tin-102.htm"
            data-date="17/06/2026 15:07" data-id="102"></li>
      </body>
    </html>
    """

    item = parse_detail_html(
        html,
        "https://baochinhphu.vn/xac-dinh-han-muc-dat-o-102260617174220224.htm",
    )

    assert item["question"] == (
        "Tình huống: Ông A hỏi về hạn mức đất ở.\n"
        "Câu hỏi: Xác định hạn mức đất ở"
    )
    assert item["published_date"] == "2026-06-17"
    assert item["retrieval_cutoff_date"] == "2026-06-17"
    assert item["article_id"] == "102260617174220224"
    assert item["tags"] == ["đất đai"]
    assert "related_articles" not in item
    assert item["expected_answer"].startswith("Bộ Nông nghiệp và Môi trường trả lời")
    assert "Không lấy tin liên quan" not in item["full_text"]
    assert "Ông A hỏi về hạn mức đất ở" in item["recommendation_text"]


def test_extract_legal_citations_keeps_bhxh_decision_references_separate() -> None:
    citations = extract_legal_citations(
        "Theo Khoản 1 Điều 72 Quyết định số 505/QĐ-BHXH ngày 27/3/2020 "
        "và Điều 46 Quyết định số 595/QĐ-BHXH, người lao động có thể..."
    )

    assert citations == [
        {
            "provision": "Khoản 1 Điều 72",
            "document_name": "Quyết định số 505/QĐ-BHXH ngày 27/3/2020",
            "document_type": "Quyết định",
            "document_number": "505/QĐ-BHXH",
            "document_date": "27/3/2020",
            "citation_text": "Khoản 1 Điều 72 Quyết định số 505/QĐ-BHXH ngày 27/3/2020",
        },
        {
            "provision": "Điều 46",
            "document_name": "Quyết định số 595/QĐ-BHXH",
            "document_type": "Quyết định",
            "document_number": "595/QĐ-BHXH",
            "document_date": None,
            "citation_text": "Điều 46 Quyết định số 595/QĐ-BHXH",
        },
    ]


def test_extract_direct_legal_document_links_from_article_body() -> None:
    links = extract_direct_legal_document_links(
        """
        <div class="detail-content">
          <p>
            Căn cứ
            <a href="https://vanban.chinhphu.vn/?pageid=27160&docid=214323">
              170/2025/NĐ-CP
            </a>
            và <a href="/not-a-legal-doc.htm">tin liên quan</a>.
          </p>
        </div>
        """,
        "https://baochinhphu.vn/test-102.htm",
    )

    assert links == [
        {
            "text": "170/2025/NĐ-CP",
            "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=214323",
            "host": "vanban.chinhphu.vn",
            "external_docid": "214323",
        }
    ]


def test_extract_related_article_candidates_for_discovery_only() -> None:
    candidates = extract_related_article_candidates(
        """
        <li class="kbwscwlrl"
            data-title="Dự án nào do tỉnh thẩm định đánh giá tác động môi trường?"
            data-url="/du-an-nao-do-tinh-tham-dinh-danh-gia-tac-dong-moi-truong-102250603110133583.htm"
            data-date="05/06/2025"
            data-id="102250603110133583"></li>
        """,
        "https://baochinhphu.vn/current-102.htm",
    )

    assert candidates == [
        {
            "title": "Dự án nào do tỉnh thẩm định đánh giá tác động môi trường?",
            "url": (
                "https://baochinhphu.vn/"
                "du-an-nao-do-tinh-tham-dinh-danh-gia-tac-dong-moi-truong-102250603110133583.htm"
            ),
            "published_date": "2025-06-05",
            "article_id": "102250603110133583",
        }
    ]


def test_parse_detail_html_matches_direct_legal_document_links_to_local_db() -> None:
    index = LegalDocumentIndex(
        [
            {
                "document_id": 179178,
                "title": "Quy định về tuyển dụng, sử dụng và quản lý công chức",
                "so_ky_hieu": "170/2025/NĐ-CP",
                "loai_van_ban": "Nghị định",
                "ngay_ban_hanh_iso": "2025-06-30",
                "tinh_trang_hieu_luc": "Còn hiệu lực",
            },
            {
                "document_id": 179106,
                "title": "Cán bộ, công chức",
                "so_ky_hieu": "80/2025/QH15",
                "loai_van_ban": "Luật",
                "ngay_ban_hanh_iso": "2025-06-24",
                "tinh_trang_hieu_luc": "Còn hiệu lực",
            },
        ]
    )
    html = """
    <html>
      <head><meta property="article:published_time" content="2026-06-17T10:39:00+07:00" /></head>
      <body>
        <a data-role="cate-name">Trả lời công dân - doanh nghiệp</a>
        <h1 class="detail-title">Điều kiện đăng ký dự tuyển công chức</h1>
        <h2 class="detail-sapo">(Chinhphu.vn) - Ông A hỏi về tuyển dụng công chức.</h2>
        <div class="detail-content">
          <p>Bộ Nội vụ trả lời vấn đề này như sau:</p>
          <p>
            Căn cứ <a href="https://vanban.chinhphu.vn/?pageid=27160&docid=214576">
              Luật Cán bộ, công chức
            </a>,
            <a href="https://vanban.chinhphu.vn/?pageid=27160&docid=214323">
              170/2025/NĐ-CP
            </a>.
          </p>
        </div>
      </body>
    </html>
    """

    item = parse_detail_html(
        html,
        "https://baochinhphu.vn/dieu-kien-dang-ky-du-tuyen-cong-chuc-102260617103941046.htm",
        legal_document_index=index,
    )

    assert item["direct_legal_document_link_count"] == 2
    assert item["matched_direct_legal_document_count"] == 2
    matched_documents = item["matched_direct_legal_documents"]
    assert matched_documents[0]["matched_documents"][0]["document_id"] == 179106
    assert matched_documents[1]["matched_documents"][0]["document_id"] == 179178


def test_direct_legal_document_matching_prefers_external_docid() -> None:
    index = LegalDocumentIndex(
        [
            {
                "document_id": 1,
                "external_docid": "111111",
                "title": "Quy định cũ",
                "so_ky_hieu": "49/2026/NĐ-CP",
                "loai_van_ban": "Nghị định",
                "ngay_ban_hanh_iso": "2026-01-01",
                "tinh_trang_hieu_luc": "Còn hiệu lực",
            },
            {
                "document_id": 2,
                "external_docid": "216860",
                "title": "Quy định đúng",
                "so_ky_hieu": "49/2026/NĐ-CP",
                "loai_van_ban": "Nghị định",
                "ngay_ban_hanh_iso": "2026-01-31",
                "tinh_trang_hieu_luc": "Còn hiệu lực",
            },
        ]
    )

    matches = index.match_link(
        {
            "text": "49/2026/NĐ-CP",
            "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=216860",
            "host": "vanban.chinhphu.vn",
            "external_docid": "216860",
        }
    )

    assert [match["document_id"] for match in matches] == [2]


def test_parse_detail_html_omits_unmatched_direct_legal_document_links() -> None:
    index = LegalDocumentIndex([])
    html = """
    <html>
      <body>
        <h1 class="detail-title">Không có văn bản trong DB</h1>
        <div class="detail-content">
          <p>Bộ Nội vụ trả lời vấn đề này như sau:</p>
          <p>
            Căn cứ <a href="https://vanban.chinhphu.vn/?pageid=27160&docid=999999">
              999/2026/NĐ-CP
            </a>.
          </p>
        </div>
      </body>
    </html>
    """

    item = parse_detail_html(
        html,
        "https://baochinhphu.vn/co-duoc-bo-thoi-gian-dong-bhxh-tai-cong-ty-no-tien-102260616160340358.htm",
        legal_document_index=index,
    )

    assert item["direct_legal_document_link_count"] == 0
    assert item["matched_direct_legal_document_count"] == 0
    assert item["direct_legal_document_links"] == []
    assert item["matched_direct_legal_documents"] == []


def test_parse_detail_html_filters_expected_citations_to_matched_documents() -> None:
    index = LegalDocumentIndex(
        [
            {
                "document_id": 179178,
                "title": "Quy định về tuyển dụng, sử dụng và quản lý công chức",
                "so_ky_hieu": "170/2025/NĐ-CP",
                "loai_van_ban": "Nghị định",
                "ngay_ban_hanh_iso": "2025-06-30",
                "tinh_trang_hieu_luc": "Còn hiệu lực",
            }
        ]
    )
    html = """
    <html>
      <body>
        <h1 class="detail-title">Điều kiện dự tuyển</h1>
        <div class="detail-content">
          <p>Bộ Nội vụ trả lời vấn đề này như sau:</p>
          <p>
            Căn cứ khoản 1 Điều 13 Nghị định số 170/2025/NĐ-CP và
            khoản 2 Điều 3 Nghị định số 999/2026/NĐ-CP.
          </p>
          <p>
            <a href="https://vanban.chinhphu.vn/?pageid=27160&docid=214323">
              170/2025/NĐ-CP
            </a>
            <a href="https://vanban.chinhphu.vn/?pageid=27160&docid=999999">
              999/2026/NĐ-CP
            </a>
          </p>
        </div>
      </body>
    </html>
    """

    item = parse_detail_html(
        html,
        "https://baochinhphu.vn/dieu-kien-du-tuyen-102.htm",
        legal_document_index=index,
    )

    assert item["direct_legal_document_link_count"] == 1
    assert item["expected_legal_citations"] == [
        {
            "provision": "khoản 1 Điều 13",
            "document_id": 179178,
            "document_name": "Quy định về tuyển dụng, sử dụng và quản lý công chức",
            "document_type": "Nghị định",
            "document_number": "170/2025/NĐ-CP",
            "document_date": "2025-06-30",
            "document_status": "Còn hiệu lực",
            "citation_text": "khoản 1 Điều 13 Nghị định số 170/2025/NĐ-CP",
        }
    ]
    assert item["expected_citation_text"] == "khoản 1 Điều 13 Nghị định số 170/2025/NĐ-CP"


def test_listing_page_urls_default_to_newest_first() -> None:
    assert listing_page_urls(max_pages=3) == [
        "https://baochinhphu.vn/tra-loi-cong-dan.htm",
        "https://baochinhphu.vn/timelinelist/102301/2.htm",
        "https://baochinhphu.vn/timelinelist/102301/3.htm",
    ]
    assert listing_page_urls(max_pages=3, newest_first=False) == [
        "https://baochinhphu.vn/timelinelist/102301/3.htm",
        "https://baochinhphu.vn/timelinelist/102301/2.htm",
        "https://baochinhphu.vn/tra-loi-cong-dan.htm",
    ]


def test_merge_items_appends_only_new_source_urls() -> None:
    existing = [
        {"source_url": "https://baochinhphu.vn/a-102.htm", "title": "old"},
    ]
    new = [
        {"source_url": "https://baochinhphu.vn/a-102.htm", "title": "duplicate"},
        {"source_url": "https://baochinhphu.vn/b-102.htm", "title": "new"},
    ]

    assert merge_items(existing, new) == [
        {"source_url": "https://baochinhphu.vn/a-102.htm", "title": "old"},
        {"source_url": "https://baochinhphu.vn/b-102.htm", "title": "new"},
    ]


def test_existing_dataset_size_controls_remaining_limit(tmp_path: Path) -> None:
    output_path = tmp_path / "rag_test_set.json"
    write_json_dataset(
        output_path,
        [
            {"source_url": "https://baochinhphu.vn/a-102.htm", "title": "a"},
            {"source_url": "https://baochinhphu.vn/b-102.htm", "title": "b"},
        ],
    )

    existing = load_existing_items(output_path)
    target_limit = 3
    new_candidates = [
        {"source_url": "https://baochinhphu.vn/c-102.htm", "title": "c"},
        {"source_url": "https://baochinhphu.vn/d-102.htm", "title": "d"},
    ]
    merged = merge_items(existing, new_candidates)

    assert max(0, target_limit - len(existing)) == 1
    assert merged[:target_limit] == [
        {"source_url": "https://baochinhphu.vn/a-102.htm", "title": "a"},
        {"source_url": "https://baochinhphu.vn/b-102.htm", "title": "b"},
        {"source_url": "https://baochinhphu.vn/c-102.htm", "title": "c"},
    ]


def test_dataset_workspace_layout_exists() -> None:
    assert (PROJECT_ROOT / "dataset" / "baochinhphu_official_qa" / "data_raw").is_dir()
    assert (PROJECT_ROOT / "dataset" / "baochinhphu_official_qa" / "data_usable").is_dir()
    assert (PROJECT_ROOT / "dataset" / "baochinhphu_official_qa" / "creation").is_dir()
