from datetime import date

import pytest
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


def test_build_filter_rejects_unknown_filter_keys() -> None:
    with pytest.raises(ValueError, match="Unsupported filter"):
        QdrantVectorStore._build_filter({"unknown": "x"})


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


def test_replace_document_chunks_deletes_existing_points_before_upsert() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_collections(self):
            return type("Collections", (), {"collections": []})()

        def create_collection(self, **_kwargs) -> None:
            self.calls.append("create")

        def delete(self, **kwargs) -> None:
            self.calls.append("delete")
            assert kwargs["collection_name"] == "chunks"
            selector = kwargs["points_selector"]
            assert selector.filter.must[0].key == "document_id"
            assert selector.filter.must[0].match.value == 42

        def upsert(self, **kwargs) -> None:
            self.calls.append("upsert")
            assert kwargs["collection_name"] == "chunks"
            assert len(kwargs["points"]) == 1

    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store.client = FakeClient()
    store.collection_name = "chunks"
    store.vector_size = 2
    store.upsert_batch_size = 64
    store._collection_ready = True

    count = store.replace_document_chunks(
        42,
        [{"chunk_id": "42:0", "document_id": 42}],
        [[0.1, 0.2]],
    )

    assert count == 1
    assert store.client.calls == ["delete", "upsert"]


def test_replace_document_chunks_rejects_non_replacement_writes() -> None:
    store = QdrantVectorStore.__new__(QdrantVectorStore)
    store._collection_ready = True
    store.client = object()
    store.collection_name = "chunks"
    store.vector_size = 2
    store.upsert_batch_size = 64

    with pytest.raises(ValueError, match="delete_existing=True"):
        store.replace_document_chunks(42, [], [], delete_existing=False)
