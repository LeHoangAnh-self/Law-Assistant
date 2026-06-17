from rag_service.index_audit import find_missing_ids


def test_find_missing_ids() -> None:
    assert find_missing_ids([3, 1, 2, 2], [2, 4]) == [1, 3]
