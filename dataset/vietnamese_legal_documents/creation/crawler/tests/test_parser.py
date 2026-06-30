from law_crawler.parser import parse_document_html


def test_parse_articles_clauses_points_tables_and_forms() -> None:
    html = """
    <div id="toanvancontent">
      <p><strong>LUẬT THỬ NGHIỆM</strong></p>
      <p>Điều 1. Phạm vi điều chỉnh</p>
      <p>1. Văn bản này quy định nguyên tắc chung.</p>
      <p>a) Nguyên tắc thứ nhất.</p>
      <p>b) Nguyên tắc thứ hai.</p>
      <table><caption>Bảng 1</caption><tr><td>Nội dung bảng</td></tr></table>
      <p>2. Quy định thêm.</p>
      <p>Điều 2. Hiệu lực thi hành</p>
      <p>1. Luật này có hiệu lực từ ngày ký.</p>
      <p>Phụ lục I Danh mục kèm theo</p>
      <a href="/Files/mau-so-01.doc">Mẫu số 01</a>
    </div>
    """

    parsed = parse_document_html(html)

    assert parsed.title == "LUẬT THỬ NGHIỆM"
    assert len(parsed.articles) == 2
    assert parsed.articles[0].number == "1"
    assert parsed.articles[0].title == "Phạm vi điều chỉnh"
    assert parsed.articles[0].stable_anchor == "article-1"
    assert [clause.number for clause in parsed.articles[0].clauses] == ["1", "2"]
    assert [point.label for point in parsed.articles[0].clauses[0].points] == ["a", "b"]
    assert parsed.articles[0].clauses[0].points[0].stable_anchor == "article-1.clause-1.point-a"
    assert len(parsed.tables) == 1
    assert parsed.tables[0].caption == "Bảng 1"
    assert parsed.tables[0].article_anchor == "article-1"
    assert len(parsed.forms) == 1
    assert parsed.forms[0].title == "Mẫu số 01"
    assert len(parsed.annexes) == 1


def test_unstructured_intro_is_kept_only_in_whole_document_text() -> None:
    html = """
    <div id="toanvancontent">
      <p>Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam;</p>
      <p>Điều 1. Điều khoản có cấu trúc</p>
      <p>Nội dung không đánh số khoản vẫn thuộc điều.</p>
    </div>
    """

    parsed = parse_document_html(html)

    assert "Căn cứ Hiến pháp" in parsed.content_text
    assert len(parsed.articles) == 1
    assert "Nội dung không đánh số khoản" in parsed.articles[0].content_text
    assert not parsed.articles[0].clauses


def test_repeated_clause_numbers_get_occurrence_anchors() -> None:
    html = """
    <div id="toanvancontent">
      <p>Điều 1. Sửa đổi nhiều điều</p>
      <p>1. Sửa đổi Điều 3 như sau:</p>
      <p>1. Nội dung khoản một được trích dẫn.</p>
      <p>2. Nội dung khoản hai được trích dẫn.</p>
      <p>2. Sửa đổi Điều 4 như sau:</p>
      <p>1. Nội dung khoản một khác.</p>
    </div>
    """

    parsed = parse_document_html(html)

    clauses = parsed.articles[0].clauses
    assert [clause.number for clause in clauses] == ["1", "1", "2", "2", "1"]
    assert [clause.occurrence_index for clause in clauses] == [1, 2, 1, 2, 3]
    assert clauses[0].stable_anchor == "article-1.clause-1"
    assert clauses[1].stable_anchor == "article-1.clause-1.occurrence-2"
    assert clauses[4].stable_anchor == "article-1.clause-1.occurrence-3"


def test_annex_content_is_not_attached_to_last_article_as_clauses() -> None:
    html = """
    <div id="toanvancontent">
      <p>Điều 5. Điều khoản thi hành</p>
      <p>1. Thông tư này có hiệu lực.</p>
      <p>Phụ lục I Danh mục</p>
      <p>1. Bảng A</p>
      <p>2. Bảng B</p>
    </div>
    """

    parsed = parse_document_html(html)

    assert [clause.number for clause in parsed.articles[0].clauses] == ["1"]
    assert len(parsed.annexes) == 1
    assert "1. Bảng A" in (parsed.annexes[0].text or "")


def test_repeated_article_numbers_get_occurrence_anchors() -> None:
    html = """
    <div id="toanvancontent">
      <p>Điều 1. Quy định chung</p>
      <p>1. Nội dung chính.</p>
      <p>Điều 2. Sửa đổi bổ sung</p>
      <p>Điều 1. Điều khoản chuyển tiếp</p>
      <p>Đối với nhiệm vụ đã phê duyệt thì tiếp tục thực hiện.</p>
    </div>
    """

    parsed = parse_document_html(html)

    assert [article.number for article in parsed.articles] == ["1", "2", "1"]
    assert [article.occurrence_index for article in parsed.articles] == [1, 1, 2]
    assert parsed.articles[0].stable_anchor == "article-1"
    assert parsed.articles[2].stable_anchor == "article-1.occurrence-2"


def test_quoted_article_marker_from_pdf_text_is_parsed() -> None:
    html = """
    <div id="toanvancontent">
      <p>- Điều 2 của Thông tư sửa đổi quy định như sau:</p>
      <p>“Điều 2. Điều khoản thi hành</p>
      <p>1. Thông tư này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2026.</p>
      <p>2. Các tổ chức, cá nhân có liên quan chịu trách nhiệm thi hành.</p>
    </div>
    """

    parsed = parse_document_html(html)

    assert len(parsed.articles) == 1
    assert parsed.articles[0].number == "2"
    assert parsed.articles[0].title == "Điều khoản thi hành"
    assert [clause.number for clause in parsed.articles[0].clauses] == ["1", "2"]


def test_inline_replacement_article_body_is_not_stored_as_title() -> None:
    html = """
    <div id="toanvancontent">
      <p>Điều 1. Sửa đổi Điều 3 như sau:</p>
      <p>"Điều 3. Thủ tục đề nghị chấp thuận xuất khẩu, nhập khẩu ngoại tệ tiền mặt của các ngân hàng được phép 1. Nguyên tắc khai, gửi, tiếp nhận, trả kết quả, trao đổi, phản hồi thông tin phải được thực hiện đúng quy định. 2. Trình tự thực hiện như sau: a) Ngân hàng được phép gửi hồ sơ đề nghị. b) Ngân hàng Nhà nước trả kết quả."</p>
    </div>
    """

    parsed = parse_document_html(html)

    replacement_article = parsed.articles[1]
    assert replacement_article.number == "3"
    assert replacement_article.title == "Thủ tục đề nghị chấp thuận xuất khẩu, nhập khẩu ngoại tệ tiền mặt của các ngân hàng được phép"
    assert len(replacement_article.title) < 1000
    assert [clause.number for clause in replacement_article.clauses] == ["1", "2"]
    assert [point.label for point in replacement_article.clauses[1].points] == ["a", "b"]


def test_legacy_roman_sections_are_parsed_as_top_level_units() -> None:
    html = """
    <div id="toanvancontent">
      <p>THÔNG TƯ LIÊN BỘ</p>
      <p>I. TIÊU CHUẨN ĂN, MẶC</p>
      <p>1. Phạm nhân được bảo đảm tiêu chuẩn ăn theo quy định.</p>
      <p>a) Tiêu chuẩn thứ nhất.</p>
      <p>II. TỔ CHỨC PHÒNG, CHỮA BỆNH</p>
      <p>1. Trại giam tổ chức phòng bệnh.</p>
    </div>
    """

    parsed = parse_document_html(html)

    assert [article.number for article in parsed.articles] == ["I", "II"]
    assert parsed.articles[0].stable_anchor == "article-i"
    assert parsed.articles[0].title == "TIÊU CHUẨN ĂN, MẶC"
    assert [clause.number for clause in parsed.articles[0].clauses] == ["1"]
    assert parsed.articles[0].clauses[0].points[0].label == "a"
    assert parsed.articles[1].title == "TỔ CHỨC PHÒNG, CHỮA BỆNH"


def test_roman_heading_does_not_interrupt_normal_article_documents() -> None:
    html = """
    <div id="toanvancontent">
      <p>Điều 1. Quy định chung</p>
      <p>I. Dòng này là nội dung của Điều 1, không phải đơn vị cấp cao.</p>
      <p>1. Khoản thuộc Điều 1.</p>
    </div>
    """

    parsed = parse_document_html(html)

    assert [article.number for article in parsed.articles] == ["1"]
    assert "I. Dòng này là nội dung" in parsed.articles[0].content_text
    assert [clause.number for clause in parsed.articles[0].clauses] == ["1"]
