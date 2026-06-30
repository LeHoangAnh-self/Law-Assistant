from rag_service.chunking import chunk_legal_text, chunk_text, normalize_text


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text(" A\n\n legal\t document ") == "A legal document"


def test_chunk_text_preserves_short_text() -> None:
    assert chunk_text("Short legal text.", chunk_size=100, overlap=10) == ["Short legal text."]


def test_chunk_text_overlaps_long_text() -> None:
    chunks = chunk_text("a" * 250, chunk_size=100, overlap=20)

    assert len(chunks) == 3
    assert chunks[0] == "a" * 100
    assert chunks[1] == "a" * 100
    assert chunks[2] == "a" * 90


def test_chunk_legal_text_prefers_article_boundaries() -> None:
    text = """
Chương I
QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh
Văn bản này quy định về phạm vi điều chỉnh.

Điều 2. Đối tượng áp dụng
Văn bản này áp dụng đối với cơ quan, tổ chức, cá nhân.
"""

    chunks = chunk_legal_text(
        text,
        chunk_size=500,
        overlap=50,
        document_context="Tiêu đề: Luật mẫu",
    )

    article_chunks = [chunk for chunk in chunks if chunk.article_number]
    assert [chunk.article_number for chunk in article_chunks] == ["1", "2"]
    assert article_chunks[0].legal_path == "Chương I > Điều 1. Phạm vi điều chỉnh"
    assert article_chunks[0].retrieval_text.startswith("Tiêu đề: Luật mẫu")
    assert (
        "Vị trí pháp lý: Chương I > Điều 1. Phạm vi điều chỉnh"
        in article_chunks[0].retrieval_text
    )


def test_chunk_legal_text_splits_long_article_by_clause() -> None:
    long_clause = " ".join(["nội dung"] * 80)
    text = f"""
Điều 3. Nghĩa vụ
1. {long_clause}
2. Cơ quan có thẩm quyền thực hiện kiểm tra.
"""

    chunks = chunk_legal_text(text, chunk_size=260, overlap=40)

    assert len(chunks) > 1
    assert {chunk.article_number for chunk in chunks} == {"3"}
    assert "1" in {chunk.clause_number for chunk in chunks}
    assert chunks[0].text.startswith("Điều 3. Nghĩa vụ")


def test_chunk_legal_text_includes_offsets_and_strategy() -> None:
    text = "Điều 1. Hiệu lực\nVăn bản này có hiệu lực từ ngày ký."

    chunks = chunk_legal_text(text, chunk_size=500, overlap=50)

    assert chunks[0].char_start == 0
    assert chunks[0].char_end == len(text)
    assert chunks[0].chunking_strategy == "legal_structure_v1"
