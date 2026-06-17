from rag_service.models import SourceReference


def build_legal_prompt(
    question: str,
    references: list[SourceReference],
    answer_language: str = "Vietnamese",
) -> str:
    citation_blocks = "\n\n".join(
        f"[{index}] Văn bản {ref.document_id}"
        f"{f' - {ref.title}' if ref.title else ''}\n"
        f"Số/Ký hiệu: {ref.document_number or 'không rõ'}\n"
        f"Ngày ban hành: {ref.issued_date or 'không rõ'}\n"
        f"Nguồn: {ref.source or 'Law Service'}\n"
        f"Trích đoạn: {ref.text}"
        for index, ref in enumerate(references, start=1)
    )
    return (
        "Bạn là trợ lý nghiên cứu pháp luật Việt Nam. Chỉ trả lời dựa trên các trích đoạn "
        "văn bản pháp luật được cung cấp. Trích dẫn nguồn ngay trong câu bằng ký hiệu như [1]. "
        "Nếu các trích đoạn không đủ căn cứ, hãy nói rõ thông tin còn thiếu và không suy đoán. "
        f"Trả lời bằng {answer_language}.\n\n"
        f"Câu hỏi:\n{question}\n\n"
        f"Các trích đoạn pháp luật:\n{citation_blocks}\n\n"
        "Trả lời:"
    )
