package com.lawassistant.lawservice.document;

import com.lawassistant.lawservice.relationship.LegalDocumentRelationship;
import java.util.List;

public record LegalDocumentDetail(
        LegalDocument document,
        String contentHtml,
        String contentText,
        List<LegalDocumentRelationship> relationships) {
}
