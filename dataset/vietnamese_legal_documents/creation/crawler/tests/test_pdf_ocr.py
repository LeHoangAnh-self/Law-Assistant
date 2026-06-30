from law_crawler.parser import parse_document_html
from law_crawler.pdf_ocr import (
    build_paddle_detector,
    normalize_paddle_boxes,
    paragraphs_to_html,
    sort_ocr_boxes_for_reading,
    split_pdf_text,
)


class NewPaddleStub:
    def __init__(self, **kwargs):
        if "cls" in kwargs or "det" in kwargs or "rec" in kwargs or "show_log" in kwargs:
            raise ValueError("Unknown argument")
        self.kwargs = kwargs


class LegacyPaddleStub:
    attempts = []

    def __init__(self, **kwargs):
        self.__class__.attempts.append(kwargs)
        if "use_doc_orientation_classify" in kwargs or "show_log" in kwargs or "cls" in kwargs:
            raise ValueError("Unknown argument")
        self.kwargs = kwargs


def test_normalize_paddle_detection_boxes_from_nested_result() -> None:
    result = [
        [
            [[10, 20], [120, 20], [120, 40], [10, 40]],
            [[10, 50], [130, 50], [130, 70], [10, 70]],
        ]
    ]

    boxes = normalize_paddle_boxes(result)

    assert boxes == [
        [(10.0, 20.0), (120.0, 20.0), (120.0, 40.0), (10.0, 40.0)],
        [(10.0, 50.0), (130.0, 50.0), (130.0, 70.0), (10.0, 70.0)],
    ]


def test_normalize_paddle_detection_boxes_from_dict_result() -> None:
    result = {"dt_polys": [[[10, 20], [120, 20], [120, 40], [10, 40]]]}

    boxes = normalize_paddle_boxes(result)

    assert boxes == [[(10.0, 20.0), (120.0, 20.0), (120.0, 40.0), (10.0, 40.0)]]


def test_normalize_paddle_detection_boxes_prefers_detection_polys_once() -> None:
    box = [[10, 20], [120, 20], [120, 40], [10, 40]]
    result = {"dt_polys": [box], "rec_polys": [box]}

    boxes = normalize_paddle_boxes(result)

    assert boxes == [[(10.0, 20.0), (120.0, 20.0), (120.0, 40.0), (10.0, 40.0)]]


def test_build_paddle_detector_prefers_new_api_arguments() -> None:
    detector = build_paddle_detector(NewPaddleStub)

    assert detector.kwargs == {
        "lang": "vi",
        "device": "cpu",
        "enable_mkldnn": False,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
    }


def test_build_paddle_detector_falls_back_to_legacy_arguments() -> None:
    LegacyPaddleStub.attempts = []

    detector = build_paddle_detector(LegacyPaddleStub)

    assert detector.kwargs == {"use_angle_cls": False, "lang": "vi", "det": True, "rec": False}


def test_sort_ocr_boxes_for_reading_orders_top_to_bottom_then_left_to_right() -> None:
    right_first_line = [(220.0, 10.0), (320.0, 10.0), (320.0, 30.0), (220.0, 30.0)]
    second_line = [(10.0, 48.0), (180.0, 48.0), (180.0, 68.0), (10.0, 68.0)]
    left_first_line = [(10.0, 12.0), (200.0, 12.0), (200.0, 32.0), (10.0, 32.0)]

    sorted_boxes = sort_ocr_boxes_for_reading([right_first_line, second_line, left_first_line])

    assert sorted_boxes == [left_first_line, right_first_line, second_line]


def test_ocr_lines_split_into_legal_paragraphs() -> None:
    text = "\n".join(
        [
            "Điều 1. Phạm vi điều chỉnh",
            "1. Văn bản này quy định nguyên tắc chung.",
            "a) Nguyên tắc thứ nhất.",
            "b) Nguyên tắc thứ hai.",
        ]
    )

    paragraphs = split_pdf_text(text)

    assert paragraphs == [
        "Điều 1. Phạm vi điều chỉnh",
        "1. Văn bản này quy định nguyên tắc chung.",
        "a) Nguyên tắc thứ nhất.",
        "b) Nguyên tắc thứ hai.",
    ]


def test_selectable_pdf_text_drops_page_numbers_and_splits_preamble() -> None:
    text = """
    THÔNG TƯ
    Hướng dẫn thực hiện mức lương cơ sở
    _____________
    Căn cứ Nghị định số 25/2025/NĐ-CP ngày 21 tháng 02 năm 2025 của Chính
    phủ quy định chức năng, nhiệm vụ, quyền hạn và cơ cấu tổ chức của Bộ Nội vụ;
    Theo đề nghị của Cục trưởng Cục Tiền lương và Bảo hiểm xã hội;
    Điều 1. Đối tượng áp dụng
    1. Cán bộ, công chức hưởng lương từ ngân sách nhà nước.
    2
    2. Viên chức hưởng lương từ quỹ lương của đơn vị sự nghiệp công lập.
    a) Nhóm thứ nhất.
    """

    paragraphs = split_pdf_text(text)

    assert "2" not in paragraphs
    assert paragraphs[:5] == [
        "THÔNG TƯ Hướng dẫn thực hiện mức lương cơ sở",
        "Căn cứ Nghị định số 25/2025/NĐ-CP ngày 21 tháng 02 năm 2025 của Chính phủ quy định chức năng, nhiệm vụ, quyền hạn và cơ cấu tổ chức của Bộ Nội vụ;",
        "Theo đề nghị của Cục trưởng Cục Tiền lương và Bảo hiểm xã hội;",
        "Điều 1. Đối tượng áp dụng",
        "1. Cán bộ, công chức hưởng lương từ ngân sách nhà nước.",
    ]


def test_selectable_pdf_paragraphs_parse_title_and_legal_hierarchy() -> None:
    paragraphs = split_pdf_text(
        """
        THÔNG TƯ
        Hướng dẫn thực hiện mức lương cơ sở
        _____________
        Căn cứ Nghị định số 25/2025/NĐ-CP;
        Điều 1. Đối tượng áp dụng
        1. Cán bộ, công chức hưởng lương từ ngân sách nhà nước.
        2. Viên chức hưởng lương từ quỹ lương của đơn vị sự nghiệp công lập.
        a) Nhóm thứ nhất.
        Điều 2. Hiệu lực thi hành
        1. Thông tư này có hiệu lực từ ngày ký.
        """
    )

    parsed = parse_document_html(paragraphs_to_html(paragraphs, source="selectable-pdf"))

    assert parsed.title == "THÔNG TƯ Hướng dẫn thực hiện mức lương cơ sở"
    assert [article.number for article in parsed.articles] == ["1", "2"]
    assert [clause.number for clause in parsed.articles[0].clauses] == ["1", "2"]
    assert parsed.articles[0].clauses[1].points[0].label == "a"
