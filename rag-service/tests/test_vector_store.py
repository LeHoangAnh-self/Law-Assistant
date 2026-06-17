from datetime import date

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
