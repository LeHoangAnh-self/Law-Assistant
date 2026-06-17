from fastapi.testclient import TestClient
from rag_service.dependencies import get_law_service_client
from rag_service.main import app


class FakeLawServiceClient:
    def __init__(self) -> None:
        self.search_call: dict | None = None

    async def search_documents(
        self,
        query: str,
        page: int = 0,
        size: int = 20,
        document_type: str | None = None,
        validity_status: str | None = None,
    ) -> dict:
        self.search_call = {
            "query": query,
            "page": page,
            "size": size,
            "document_type": document_type,
            "validity_status": validity_status,
        }
        return {
            "content": [{"id": 42, "title": "Test law", "documentNumber": "42/2026"}],
            "number": page,
            "totalPages": 1,
            "totalElements": 1,
            "last": True,
        }

    async def get_document_detail(self, document_id: int) -> dict:
        return {
            "document": {"id": document_id, "title": "Test law"},
            "contentText": "Document body",
            "contentHtml": None,
            "relationships": [],
        }


def test_document_picker_serves_static_page() -> None:
    client = TestClient(app)

    response = client.get("/documents")

    assert response.status_code == 200
    assert "Choose a document from the database" in response.text


def test_document_api_proxies_law_service_search_and_detail() -> None:
    fake_client = FakeLawServiceClient()
    app.dependency_overrides[get_law_service_client] = lambda: fake_client
    client = TestClient(app)

    try:
        search_response = client.get(
            "/api/documents",
            params={
                "query": "tax",
                "documentType": "Decree",
                "validityStatus": "ACTIVE",
                "page": 2,
                "size": 5,
            },
        )
        detail_response = client.get("/api/documents/42")
    finally:
        app.dependency_overrides.clear()

    assert search_response.status_code == 200
    assert search_response.json()["content"][0]["id"] == 42
    assert fake_client.search_call == {
        "query": "tax",
        "page": 2,
        "size": 5,
        "document_type": "Decree",
        "validity_status": "ACTIVE",
    }
    assert detail_response.status_code == 200
    assert detail_response.json()["contentText"] == "Document body"
