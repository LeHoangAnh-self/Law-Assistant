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


def test_article_only_chunk_is_parent_chunk() -> None:
    text = "Điều 1. Hiệu lực\nVăn bản này có hiệu lực từ ngày ký."

    chunks = chunk_legal_text(text, chunk_size=500, overlap=50)

    assert len(chunks) == 1
    assert chunks[0].chunk_level == "parent"
    assert chunks[0].parent_article_number == "1"
    assert chunks[0].parent_text == text
    assert chunks[0].child_text is None


def test_article_clause_chunks_include_parent_and_child_metadata() -> None:
    text = """
Điều 2. Quyền và nghĩa vụ
1. Cá nhân có quyền yêu cầu cung cấp thông tin.
2. Cơ quan có nghĩa vụ trả lời đúng hạn.
"""

    chunks = chunk_legal_text(text, chunk_size=500, overlap=50)
    parent = next(chunk for chunk in chunks if chunk.chunk_level == "parent")
    children = [chunk for chunk in chunks if chunk.chunk_level == "child"]

    assert parent.article_number == "2"
    assert [chunk.clause_number for chunk in children] == ["1", "2"]
    assert all(chunk.parent_key == parent.parent_key for chunk in children)
    assert all(chunk.parent_article_number == "2" for chunk in children)
    assert all(chunk.parent_text == parent.text for chunk in children)
    assert children[0].child_text == children[0].text


def test_article_clause_point_chunks_use_point_children() -> None:
    text = """
Điều 3. Hồ sơ
1. Hồ sơ bao gồm:
a) Đơn đề nghị.
b) Bản sao giấy tờ.
2. Cơ quan tiếp nhận kiểm tra hồ sơ.
"""

    chunks = chunk_legal_text(text, chunk_size=500, overlap=50)
    children = [chunk for chunk in chunks if chunk.chunk_level == "child"]

    assert [(chunk.clause_number, chunk.point_number) for chunk in children] == [
        ("1", "a"),
        ("1", "b"),
        ("2", None),
    ]
    assert children[0].legal_path == "Điều 3. Hồ sơ"
    assert "Đơn đề nghị" in children[0].child_text


def test_malformed_text_uses_fixed_window_fallback() -> None:
    text = " ".join(["nội dung không có cấu trúc điều khoản"] * 30)

    chunks = chunk_legal_text(text, chunk_size=120, overlap=20)

    assert len(chunks) > 1
    assert all(chunk.chunk_level == "parent" for chunk in chunks)
    assert all(chunk.article_number is None for chunk in chunks)
