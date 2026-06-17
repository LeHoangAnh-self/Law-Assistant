from rag_service.chunking import chunk_text, normalize_text


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
