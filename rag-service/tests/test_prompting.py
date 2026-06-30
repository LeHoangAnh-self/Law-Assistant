from rag_service.models import SourceReference
from rag_service.prompting import build_legal_prompt


def test_prompt_contains_question_and_citations() -> None:
    prompt = build_legal_prompt(
        "Văn bản này còn hiệu lực không?",
        [
            SourceReference(
                document_id=42,
                chunk_id="42:0",
                title="Một văn bản luật",
                document_number="LAW-42",
                document_type="Luật",
                validity_status="Còn hiệu lực",
                source="source-url",
                issued_date="2026-01-01",
                effective_date="2026-02-01",
                issuing_authority="Quốc hội",
                scope="Toàn quốc",
                score=0.9,
                text="Văn bản này còn hiệu lực.",
            )
        ],
        issue_label="labor: resignation",
        required_source_checklist=["Bộ luật Lao động 2019 Điều 35"],
        missing_required_sources=["Bộ luật Lao động 2019 Điều 40"],
    )

    assert "Văn bản này còn hiệu lực không?" in prompt
    assert "[1] Văn bản 42" in prompt
    assert "Loại văn bản: Luật" in prompt
    assert "Cơ quan ban hành: Quốc hội" in prompt
    assert "Phạm vi: Toàn quốc" in prompt
    assert "Văn bản này còn hiệu lực." in prompt
    assert "không áp dụng Pháp lệnh/khung thuế thu nhập" in prompt
    assert "Áp dụng vào từng người/từng sự kiện" in prompt
    assert "tách phần nghĩa vụ theo tỷ lệ sở hữu" in prompt
    assert "nguồn cụ thể nhất và trực tiếp nhất" in prompt
    assert "không quá khoảng 650 từ" in prompt
    assert "'đủ điều kiện', 'không đủ điều kiện', hoặc 'chưa đủ dữ kiện'" in prompt
    assert "Luật làm nền tảng, Nghị định nếu" in prompt
    assert "miễn thuế nhà ở duy nhất + đồng sở hữu" in prompt
    assert "Điều 12 Thông tư 111/2013/TT-BTC" in prompt
    assert "Điều 35 Bộ luật Lao động 2019" in prompt
    assert "Điều 40 về nghĩa vụ chỉ khi" in prompt
    assert "không được dùng việc không chốt/xác nhận" in prompt
    assert "không cảnh báo chung chung" in prompt
    assert "Issue classifier:" in prompt
    assert "Required-source checklist" in prompt
    assert "Nếu checklist nguồn kiểm soát chưa đủ" in prompt
    assert "Không viết đoạn, tiêu đề hoặc câu bắt đầu bằng 'Tự kiểm tra:'" in prompt
