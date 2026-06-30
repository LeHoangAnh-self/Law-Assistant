from datetime import date

from rag_service.models import SourceReference
from rag_service.vector_store import QdrantVectorStore


def test_build_filter_includes_issued_date_cutoff() -> None:
    query_filter = QdrantVectorStore._build_filter(
        {"document_type": "Nghị định"},
        issued_date_lte=date(2025, 3, 6),
    )

    assert query_filter is not None
    assert len(query_filter.must) == 2
    assert query_filter.must[0].key == "document_type"
    assert query_filter.must[1].key == "issued_date"
    assert query_filter.must[1].range.lte == date(2025, 3, 6)


def test_batched_splits_items_by_configured_size() -> None:
    batches = QdrantVectorStore._batched([1, 2, 3, 4, 5], 2)

    assert batches == [[1, 2], [3, 4], [5]]


def test_adjacent_chunks_uses_numeric_chunk_order() -> None:
    chunks = [
        SourceReference(document_id=1, chunk_id="1:1", score=0, text="one"),
        SourceReference(document_id=1, chunk_id="1:2", score=0, text="two"),
        SourceReference(document_id=1, chunk_id="1:10", score=0, text="ten"),
    ]
    sorted_chunks = sorted(chunks, key=QdrantVectorStore._chunk_sort_key)

    adjacent = QdrantVectorStore.get_adjacent_chunks(sorted_chunks, "1:2", window=1)

    assert [chunk.chunk_id for chunk in adjacent] == ["1:1", "1:10"]
