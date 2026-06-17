from datetime import UTC, datetime

from rag_service.models import EmbeddingUpdateEvent


def test_embedding_event_accepts_iso_timestamp() -> None:
    event = EmbeddingUpdateEvent.model_validate(
        {
            "documentId": 4260,
            "reason": "DOCUMENT_UPDATED",
            "requestedAt": "2026-06-16T16:26:22.102+07:00",
        }
    )

    assert event.documentId == 4260
    assert event.requestedAt is not None
    assert event.requestedAt.isoformat() == "2026-06-16T16:26:22.102000+07:00"


def test_embedding_event_accepts_spring_numeric_timestamp() -> None:
    event = EmbeddingUpdateEvent.model_validate(
        {
            "documentId": 4260,
            "reason": "DOCUMENT_UPDATED",
            "requestedAt": 1781625073.7497044,
        }
    )

    assert event.documentId == 4260
    assert event.requestedAt == datetime.fromtimestamp(1781625073.7497044, tz=UTC)
