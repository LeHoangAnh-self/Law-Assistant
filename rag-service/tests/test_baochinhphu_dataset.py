from rag_service.baochinhphu_dataset import parse_detail_html


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
    assert item["related_articles"][0]["article_id"] == "102"
    assert item["expected_answer"].startswith("Bộ Nông nghiệp và Môi trường trả lời")
    assert "Không lấy tin liên quan" not in item["full_text"]
    assert "Ông A hỏi về hạn mức đất ở" in item["recommendation_text"]
