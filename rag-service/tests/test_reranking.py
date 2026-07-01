from rag_service.models import SourceReference
from rag_service.reranking import CrossEncoderReranker


def reference(document_id: int, chunk_number: int, score: float) -> SourceReference:
    return SourceReference(
        document_id=document_id,
        chunk_id=f"{document_id}:{chunk_number}",
        score=score,
        text=f"chunk {chunk_number}",
    )


def rich_reference(
    document_id: int,
    title: str,
    text: str,
    score: float,
    issued_date: str,
    validity_status: str = "Còn hiệu lực",
) -> SourceReference:
    return SourceReference(
        document_id=document_id,
        chunk_id=f"{document_id}:1",
        title=title,
        issued_date=issued_date,
        validity_status=validity_status,
        score=score,
        text=text,
    )


def test_disabled_reranker_diversifies_documents_before_backfill() -> None:
    reranker = CrossEncoderReranker("unused", enabled=False)
    references = [
        reference(1, 1, 0.9),
        reference(1, 2, 0.8),
        reference(1, 3, 0.7),
        reference(2, 1, 0.6),
        reference(3, 1, 0.5),
    ]

    result = reranker.rerank("query", references, limit=4)

    assert [item.chunk_id for item in result] == ["1:1", "1:2", "2:1", "3:1"]


def test_reranker_can_prefix_query_instruction() -> None:
    reranker = CrossEncoderReranker(
        "unused",
        enabled=False,
        query_instruction="Legal task\nQuery: ",
    )

    assert reranker._rerank_query("Điều 35 là gì?") == "Legal task\nQuery: Điều 35 là gì?"


def test_current_tax_query_demotes_obsolete_high_income_tax_sources() -> None:
    reranker = CrossEncoderReranker("unused", enabled=False)
    obsolete = rich_reference(
        10485,
        "Nghị định năm 1993 về Pháp lệnh thuế thu nhập đối với người có thu nhập cao",
        "thu nhập cao bán nhà giá vốn biểu thuế lũy tiến",
        9.0,
        "1993-03-23",
    )
    current = rich_reference(
        187045,
        "Luật Thuế thu nhập cá nhân",
        "chuyển nhượng bất động sản giá chuyển nhượng nhân với thuế suất 2%",
        3.0,
        "2025-12-10",
    )

    result = reranker.rerank(
        "thuế thu nhập cá nhân chuyển nhượng bất động sản giá chuyển nhượng",
        [obsolete, current],
        limit=2,
    )

    assert result[0].document_id == 187045


def test_exemption_query_boosts_only_home_and_co_owner_sources() -> None:
    reranker = CrossEncoderReranker("unused", enabled=False)
    circular_111 = rich_reference(
        1112013,
        "Thông tư 111/2013/TT-BTC hướng dẫn Luật Thuế thu nhập cá nhân",
        (
            "Điều 3 miễn thuế thu nhập cá nhân chuyển nhượng nhà ở, quyền sử dụng đất ở "
            "duy nhất. Trường hợp đồng sở hữu thì nghĩa vụ thuế xác định theo từng cá nhân."
        ),
        1.0,
        "2013-08-15",
    )
    nonresident = rich_reference(
        187045,
        "Luật Thuế thu nhập cá nhân",
        "cá nhân không cư trú chuyển nhượng bất động sản giá chuyển nhượng nhân thuế suất 2%",
        5.0,
        "2025-12-10",
        validity_status="Chưa có hiệu lực",
    )
    business = rich_reference(
        186852,
        "Nghị định về nhà ở, kinh doanh bất động sản",
        "dự án bất động sản nhà ở xã hội chuyển nhượng hợp đồng",
        4.0,
        "2026-02-09",
    )

    result = reranker.rerank(
        "miễn thuế TNCN nhà ở duy nhất vợ chồng đồng sở hữu vợ có đất riêng",
        [nonresident, business, circular_111],
        limit=3,
    )

    assert result[0].document_id == 1112013


def test_pit_transfer_query_penalizes_customs_and_non_agricultural_land_tax_noise() -> None:
    reranker = CrossEncoderReranker("unused", enabled=False)
    circular_111_article_12 = rich_reference(
        1112013,
        "Thông tư 111/2013/TT-BTC",
        "Điều 12 chuyển nhượng bất động sản đồng sở hữu nghĩa vụ thuế được xác định riêng tỷ lệ bình quân",
        1.0,
        "2013-08-15",
        validity_status="Hết hiệu lực một phần",
    )
    customs = rich_reference(
        142826,
        "Nghị định về hải quan hàng miễn thuế",
        "Chi cục Hải quan quản lý cửa hàng miễn thuế hàng miễn thuế",
        8.0,
        "2020-06-15",
    )
    land_tax = rich_reference(
        27162,
        "Thông tư hướng dẫn thuế sử dụng đất phi nông nghiệp",
        "thuế sử dụng đất phi nông nghiệp miễn thuế",
        7.0,
        "2011-11-11",
        validity_status="Hết hiệu lực một phần",
    )

    result = reranker.rerank(
        "TNCN chuyển nhượng bất động sản đồng sở hữu nhà ở duy nhất tỷ lệ bình quân",
        [customs, land_tax, circular_111_article_12],
        limit=3,
    )

    assert result[0].document_id == 1112013


def test_only_home_exemption_query_penalizes_salary_border_trade_and_natural_resource_tax() -> None:
    reranker = CrossEncoderReranker("unused", enabled=False)
    article_3 = rich_reference(
        1112013,
        "Thông tư 111/2013/TT-BTC",
        "Điều 3 miễn thuế TNCN chuyển nhượng nhà ở duy nhất, đất ở duy nhất",
        1.0,
        "2013-08-15",
        validity_status="Hết hiệu lực một phần",
    )
    salary = rich_reference(
        37590,
        "Thông tư 111/2013/TT-BTC",
        "Thu nhập từ tiền lương, tiền công, phụ cấp, trợ cấp",
        9.0,
        "2013-08-15",
    )
    border_trade = rich_reference(
        128277,
        "Nghị định thương mại biên giới",
        "cư dân biên giới được hưởng định mức miễn thuế nhập khẩu",
        8.0,
        "2018-01-23",
    )
    natural_resource = rich_reference(
        12660,
        "Nghị định thuế tài nguyên",
        "miễn thuế tài nguyên đối với khai thác không nhằm mục đích kinh doanh",
        8.0,
        "2009-01-19",
    )

    result = reranker.rerank(
        "miễn thuế TNCN chuyển nhượng căn hộ nhà ở duy nhất vợ chồng đồng sở hữu",
        [salary, border_trade, natural_resource, article_3],
        limit=4,
    )

    assert result[0].document_id == 1112013


def test_labor_resignation_query_boosts_employee_article_35_over_employer_notice_noise() -> None:
    reranker = CrossEncoderReranker("unused", enabled=False)
    article_35 = rich_reference(
        139264,
        "Bộ Luật lao động số 45/2019/QH14",
        (
            "Điều 35. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động "
            "không cần báo trước nếu không được trả đủ lương hoặc trả lương không đúng thời hạn "
            "hoặc không được bố trí theo đúng công việc, địa điểm làm việc."
        ),
        1.0,
        "2019-11-20",
        validity_status="Hết hiệu lực một phần",
    )
    employer_notice = rich_reference(
        139264,
        "Bộ Luật lao động số 45/2019/QH14",
        "Điều 36. Người sử dụng lao động phải báo trước cho người lao động ít nhất 45 ngày.",
        8.0,
        "2019-11-20",
        validity_status="Hết hiệu lực một phần",
    )
    unemployment = rich_reference(
        186281,
        "Nghị định về bảo hiểm thất nghiệp",
        "Mức đóng bảo hiểm thất nghiệp của người lao động và người sử dụng lao động.",
        7.0,
        "2025-12-31",
    )

    result = reranker.rerank(
        "nghỉ việc không báo trước vì trả lương trễ đổi địa điểm làm việc không chốt BHXH",
        [employer_notice, unemployment, article_35],
        limit=3,
    )

    assert result[0].text.startswith("Điều 35")
