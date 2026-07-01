import httpx
from rag_service.worker import index_document


class FakeLawServiceClient:
    updates: list[tuple[int, str]] = []

    def __init__(self, base_url: str, admin_token: str | None = None) -> None:
        self.base_url = base_url
        self.admin_token = admin_token

    def update_embedding_status_sync(self, document_id: int, status: str) -> None:
        self.updates.append((document_id, status))


def test_index_document_retry_policy_avoids_immediate_retry() -> None:
    assert index_document.retry_backoff == 10
    assert index_document.retry_jitter is False


def test_retry_hook_marks_document_pending(monkeypatch) -> None:
    FakeLawServiceClient.updates = []
    monkeypatch.setattr("rag_service.worker.LawServiceClient", FakeLawServiceClient)

    index_document.on_retry(httpx.ConnectError("connection refused"), "task-id", (42,), {}, None)

    assert FakeLawServiceClient.updates == [(42, "PENDING")]


def test_failure_hook_marks_document_failed(monkeypatch) -> None:
    FakeLawServiceClient.updates = []
    monkeypatch.setattr("rag_service.worker.LawServiceClient", FakeLawServiceClient)

    index_document.on_failure(RuntimeError("boom"), "task-id", (42,), {}, None)

    assert FakeLawServiceClient.updates == [(42, "FAILED")]
