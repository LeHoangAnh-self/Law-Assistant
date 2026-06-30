import httpx
from qdrant_client.http.exceptions import UnexpectedResponse
from rag_service.index_audit import fetch_qdrant_indexed_document_ids, find_missing_ids


def test_find_missing_ids() -> None:
    assert find_missing_ids([3, 1, 2, 2], [2, 4]) == [1, 3]


class MissingCollectionQdrantClient:
    def scroll(self, **_kwargs):
        raise UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            content=(
                b'{"status":{"error":"Not found: Collection '
                b"`legal_document_chunks` doesn't exist!\"}}"
            ),
            headers=httpx.Headers(),
        )


def test_fetch_qdrant_indexed_document_ids_returns_empty_set_when_collection_is_missing(
    capsys,
) -> None:
    indexed_ids = fetch_qdrant_indexed_document_ids(
        "http://localhost:6333",
        "legal_document_chunks",
        1000,
        client=MissingCollectionQdrantClient(),
    )

    assert indexed_ids == set()
    assert "does not exist yet" in capsys.readouterr().out
