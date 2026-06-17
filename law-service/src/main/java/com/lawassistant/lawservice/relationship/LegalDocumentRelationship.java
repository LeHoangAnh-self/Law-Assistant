package com.lawassistant.lawservice.relationship;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
        name = "legal_document_relationships",
        uniqueConstraints = @UniqueConstraint(
                name = "uk_legal_doc_relationship",
                columnNames = {"document_id", "related_document_id", "relationship_type"}))
public class LegalDocumentRelationship {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "document_id", nullable = false)
    private Long documentId;

    @Column(name = "related_document_id", nullable = false)
    private Long relatedDocumentId;

    @Column(name = "relationship_type", nullable = false, length = 255)
    private String relationshipType;

    public Long getId() { return id; }
    public Long getDocumentId() { return documentId; }
    public void setDocumentId(Long documentId) { this.documentId = documentId; }
    public Long getRelatedDocumentId() { return relatedDocumentId; }
    public void setRelatedDocumentId(Long relatedDocumentId) { this.relatedDocumentId = relatedDocumentId; }
    public String getRelationshipType() { return relationshipType; }
    public void setRelationshipType(String relationshipType) { this.relationshipType = relationshipType; }
}
