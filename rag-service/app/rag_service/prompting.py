from rag_service.models import SourceReference


def build_legal_prompt(
    question: str,
    references: list[SourceReference],
    answer_language: str = "Vietnamese",
    conversation_context: str | None = None,
    as_of_date=None,
    issue_label: str | None = None,
    required_source_checklist: list[str] | None = None,
    missing_required_sources: list[str] | None = None,
) -> str:
    citation_blocks = "\n\n".join(
        f"[{index}] Văn bản {ref.document_id}"
        f"{f' - {ref.title}' if ref.title else ''}\n"
        f"Số/Ký hiệu: {ref.document_number or 'không rõ'}\n"
        f"Loại văn bản: {ref.document_type or 'không rõ'}\n"
        f"Tình trạng hiệu lực: {ref.validity_status or 'không rõ'}\n"
        f"Ngày ban hành: {ref.issued_date or 'không rõ'}\n"
        f"Ngày hiệu lực: {ref.effective_date or 'không rõ'}\n"
        f"Ngày hết hiệu lực: {ref.expired_date or 'không rõ'}\n"
        f"Cơ quan ban hành: {ref.issuing_authority or 'không rõ'}\n"
        f"Phạm vi: {ref.scope or 'không rõ'}\n"
        f"Vị trí: {ref.legal_path or 'không rõ'}\n"
        f"Nguồn: {ref.source_url or ref.source or 'Law Service'}\n"
        f"Trích đoạn: {ref.text}"
        for index, ref in enumerate(references, start=1)
    )
    context_block = (
        f"Ngữ cảnh hội thoại trước đó, chỉ dùng để hiểu đại từ hoặc câu hỏi tiếp nối:\n"
        f"{conversation_context}\n\n"
        if conversation_context
        else ""
    )
    as_of_line = f"Ngày đánh giá pháp lý: {as_of_date.isoformat()}.\n" if as_of_date else ""
    issue_line = f"Issue classifier: {issue_label}.\n" if issue_label else ""
    required_lines = required_source_checklist or []
    missing_lines = missing_required_sources or []
    checklist_block = (
        "Required-source checklist cho vấn đề này (các nguồn kiểm soát ưu tiên phải có trước khi kết luận):\n"
        + "\n".join(f"- {item}" for item in required_lines)
        + "\n\n"
        if required_lines
        else ""
    )
    missing_block = (
        "Các nguồn kiểm soát đang thiếu trong trích đoạn hiện tại:\n"
        + "\n".join(f"- {item}" for item in missing_lines)
        + "\n\n"
        if missing_lines
        else ""
    )
    return (
        "Bạn là trợ lý nghiên cứu pháp luật Việt Nam. Chỉ trả lời dựa trên các trích đoạn "
        "văn bản pháp luật được cung cấp. Trích dẫn nguồn ngay trong câu bằng ký hiệu như [1]. "
        "Nếu các trích đoạn không đủ căn cứ, hãy nói rõ thông tin còn thiếu và không suy đoán. "
        "Hãy trả lời thân thiện với người đọc: nêu kết luận ngắn trước, giải thích căn cứ pháp lý "
        "bằng ngôn ngữ dễ hiểu, chỉ rõ điều/khoản hoặc vị trí nếu có, và trích một phần nội dung "
        "quan trọng từ văn bản khi cần để người đọc thấy căn cứ nằm ở đâu. "
        "Không chỉ liệt kê tên văn bản. "
        "Chỉ dùng citation cho ý mà trích đoạn đó trực tiếp chứng minh; không cite nguồn yếu, "
        "nguồn chỉ liên quan gián tiếp, hoặc nguồn không chứa nội dung đang nói. "
        "Khi có nhiều nguồn cùng hỗ trợ một ý, cite nguồn cụ thể nhất và trực tiếp nhất; ví dụ "
        "Thông tư hướng dẫn chi tiết được ưu tiên cho điều kiện/hồ sơ/cách chia theo đồng sở hữu, "
        "còn Luật/Nghị định dùng cho nền tảng pháp lý chung. "
        "Nếu một trích đoạn được truy xuất nhưng không thật sự hỗ trợ câu trả lời, hãy bỏ qua nó. "
        "Khi có luật/nghị định mới và văn bản hướng dẫn cũ cùng xuất hiện, ưu tiên văn bản hiện hành "
        "và nói rõ nếu văn bản cũ chỉ có giá trị tham khảo. "
        "Đối với câu hỏi về nghĩa vụ thuế hiện tại, không áp dụng Pháp lệnh/khung thuế thu nhập "
        "đối với người có thu nhập cao hoặc văn bản trước Luật Thuế thu nhập cá nhân 2007, trừ khi "
        "người dùng hỏi rõ về giai đoạn lịch sử đó. "
        "Nếu nguồn truy xuất chỉ là văn bản cũ/hết hiệu lực hoặc có dấu hiệu không phù hợp thời kỳ, "
        "không được tính số tiền cụ thể; hãy nói cần nguồn hiện hành. "
        "Với câu hỏi tư vấn, phải áp dụng luật riêng cho từng người nếu tài sản có nhiều chủ sở hữu; "
        "đừng kết luận chung cho toàn bộ tài sản khi tình trạng miễn thuế của từng đồng sở hữu khác nhau. "
        "Nếu chỉ một đồng sở hữu đủ điều kiện miễn, hãy tách phần nghĩa vụ theo tỷ lệ sở hữu hoặc theo "
        "phần bằng nhau khi không có tài liệu xác định tỷ lệ. "
        "Khi dữ kiện người dùng nêu rõ khớp hoặc không khớp điều kiện pháp luật, hãy kết luận dứt khoát "
        "cho từng bên là 'đủ điều kiện', 'không đủ điều kiện', hoặc 'chưa đủ dữ kiện'; không chỉ nói "
        "'có rủi ro' nếu căn cứ đã rõ. "
        "Với câu trả lời về miễn thuế, cố gắng dẫn đủ hệ thống nguồn: Luật làm nền tảng, Nghị định nếu "
        "quy định điều kiện, và Thông tư cho hướng dẫn chi tiết/hồ sơ/thủ tục. "
        "Riêng vấn đề 'miễn thuế nhà ở duy nhất + đồng sở hữu', bắt buộc kiểm tra và sử dụng nếu có trong "
        "trích đoạn: Điều 3 Thông tư 111/2013/TT-BTC cho điều kiện miễn thuế và quy tắc vợ/chồng có nhà, "
        "đất ở riêng; Điều 12 Thông tư 111/2013/TT-BTC cho phân bổ nghĩa vụ thuế giữa đồng sở hữu và "
        "cách chia bình quân khi không có tài liệu hợp pháp về tỷ lệ sở hữu. "
        "Nếu thiếu một trong hai nhóm nguồn này, phải nói rõ phần còn thiếu thay vì suy đoán. "
        "Riêng vấn đề lao động về nghỉ việc ngay do chậm lương, đổi địa điểm làm việc, giữ lương cuối "
        "hoặc chốt BHXH, bắt buộc kiểm tra nếu có trong trích đoạn: Điều 35 Bộ luật Lao động 2019 "
        "về quyền người lao động đơn phương chấm dứt không cần báo trước; Điều 40 về nghĩa vụ chỉ khi "
        "người lao động đơn phương chấm dứt trái pháp luật; Điều 48 về thanh toán quyền lợi, xác nhận "
        "thời gian đóng bảo hiểm xã hội/bảo hiểm thất nghiệp và trả giấy tờ; Điều 97 về trả lương đúng "
        "hạn, trường hợp chậm lương do bất khả kháng và khoản trả thêm khi chậm từ 15 ngày trở lên. "
        "Nếu dữ kiện người dùng khớp căn cứ Điều 35 như không được trả đủ/đúng hạn hoặc không được bố trí "
        "đúng địa điểm làm việc đã thỏa thuận, hãy kết luận có cơ sở mạnh để nghỉ ngay không cần báo trước, "
        "chỉ đặt điều kiện kiểm tra ngoại lệ hợp pháp như chậm lương do bất khả kháng hoặc điều chuyển "
        "tạm thời hợp pháp; không chỉ trả lời 'chưa đủ căn cứ' khi trích đoạn đã có Điều 35. "
        "Về BHXH, nếu có Điều 48 thì phải nói công ty không được dùng việc không chốt/xác nhận quá trình "
        "đóng BHXH, BHTN hoặc giữ giấy tờ làm sức ép, kể cả khi còn tranh chấp về việc nghỉ đúng hay sai. "
        "Khi văn bản có tình trạng 'hết hiệu lực một phần', không cảnh báo chung chung. Hãy đánh giá ở "
        "cấp điều/khoản đang viện dẫn: nếu trích đoạn và metadata không cho thấy điều/khoản đó đã hết "
        "hiệu lực hoặc bị thay thế thì có thể dùng thận trọng và nói 'văn bản hết hiệu lực một phần, "
        "nhưng trích đoạn không thể hiện điều/khoản này đã hết hiệu lực'; nếu nguồn cho thấy chính "
        "điều/khoản đó hết hiệu lực thì không dùng làm căn cứ chính. "
        "Cuối câu hoặc cuối ý phải có citation như [1], [2]. "
        "Nếu các nguồn có khác biệt hoặc chỉ liên quan một phần, hãy nói rõ mức độ chắc chắn. "
        "Nếu checklist nguồn kiểm soát chưa đủ, phải nêu rõ thiếu nguồn nào và chỉ đưa kết luận tạm thời, "
        "không kết luận dứt khoát theo hướng có lợi/bất lợi cho bất kỳ bên nào. "
        "Giữ câu trả lời ngắn gọn, ưu tiên kết luận rõ; không quá khoảng 650 từ. "
        "Không kết thúc giữa câu hoặc giữa ý. "
        f"Trả lời bằng {answer_language}.\n\n"
        f"{context_block}"
        f"{issue_line}"
        f"{checklist_block}"
        f"{missing_block}"
        f"{as_of_line}"
        f"Câu hỏi hiện tại cần trả lời:\n{question}\n\n"
        f"Các trích đoạn pháp luật:\n{citation_blocks}\n\n"
        "Định dạng trả lời:\n"
        "1. Kết luận\n"
        "2. Luật áp dụng tại ngày nêu trong câu hỏi\n"
        "3. Áp dụng vào từng người/từng sự kiện\n"
        "4. Phân tích rủi ro\n"
        "5. Giấy tờ cần kiểm tra\n"
        "6. Khuyến nghị thực tế\n"
        "7. Điều gì có thể làm thay đổi câu trả lời\n"
        "Ẩn khỏi câu trả lời cuối cùng: tự kiểm tra ngắn gọn rằng đã có kết luận rõ cho từng bên, "
        "luật kiểm soát, áp dụng đủ dữ kiện chính, ngoại lệ/rủi ro, giấy tờ và bước tiếp theo. "
        "Không viết đoạn, tiêu đề hoặc câu bắt đầu bằng 'Tự kiểm tra:' trong câu trả lời cho người dùng.\n\n"
        "Trả lời:"
    )
