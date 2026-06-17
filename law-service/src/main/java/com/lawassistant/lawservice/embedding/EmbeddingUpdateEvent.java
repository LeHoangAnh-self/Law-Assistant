package com.lawassistant.lawservice.embedding;

import java.time.OffsetDateTime;

public record EmbeddingUpdateEvent(Long documentId, String reason, OffsetDateTime requestedAt) {
    public static EmbeddingUpdateEvent documentUpdated(Long documentId) {
        return new EmbeddingUpdateEvent(documentId, "DOCUMENT_UPDATED", OffsetDateTime.now());
    }
}
