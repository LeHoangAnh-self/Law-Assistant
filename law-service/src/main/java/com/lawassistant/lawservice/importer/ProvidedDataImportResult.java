package com.lawassistant.lawservice.importer;

public record ProvidedDataImportResult(long metadataRows, long contentRows, long relationshipRows, boolean embeddingEventsPublished) {
}
