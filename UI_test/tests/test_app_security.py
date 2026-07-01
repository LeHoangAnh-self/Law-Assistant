from typing import Any
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as ui_app


class FakeResponse:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {
            "document": {
                "id": 123,
                "title": "Unsafe source",
                "sourceUrl": "javascript:alert(1)",
            },
            "contentText": "body",
            "relationships": [],
        }


class FakeAsyncClient:
    def __init__(self, timeout: int) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def get(self, _url: str) -> FakeResponse:
        return FakeResponse()


def test_openai_key_test_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setattr(ui_app, "ENABLE_OPENAI_KEY_TEST", False)
    client = TestClient(ui_app.app)

    response = client.post(
        "/api/openai/test",
        json={"api_key": "sk-" + "x" * 40, "model": "gpt-5.5"},
    )

    assert response.status_code == 403


def test_document_proxy_removes_unsafe_source_url(monkeypatch) -> None:
    monkeypatch.setattr(ui_app.httpx, "AsyncClient", FakeAsyncClient)
    client = TestClient(ui_app.app)

    response = client.get("/api/documents/123")

    assert response.status_code == 200
    document = response.json()["document"]
    assert "sourceUrl" not in document
    assert document["sourceUrlText"] == "javascript:alert(1)"
