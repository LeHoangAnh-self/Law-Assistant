package com.lawassistant.lawservice.relationship;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface LegalDocumentRelationshipRepository extends JpaRepository<LegalDocumentRelationship, Long> {
    List<LegalDocumentRelationship> findByDocumentId(Long documentId);
}
