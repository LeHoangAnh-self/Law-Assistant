package com.lawassistant.lawservice.document;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;

@Entity
@Table(name = "legal_documents")
public class LegalDocument {

    @Id
    private Long id;

    @Column(nullable = false, length = 1500)
    private String title;

    @Column(name = "document_number", length = 255)
    private String documentNumber;

    @Column(name = "issued_date")
    private LocalDate issuedDate;

    @Column(name = "document_type", length = 255)
    private String documentType;

    @Column(name = "effective_date")
    private LocalDate effectiveDate;

    @Column(name = "expired_date")
    private LocalDate expiredDate;

    @Column(name = "source", length = 500)
    private String source;

    @Column(name = "gazette_date_raw", length = 255)
    private String gazetteDateRaw;

    @Column(name = "sector", length = 255)
    private String sector;

    @Column(name = "field", length = 1000)
    private String field;

    @Column(name = "issuing_authority", length = 500)
    private String issuingAuthority;

    @Column(name = "signer_title", length = 255)
    private String signerTitle;

    @Column(name = "signer_name", length = 255)
    private String signerName;

    @Column(name = "scope", length = 500)
    private String scope;

    @Column(name = "application_info")
    private Double applicationInfo;

    @Column(name = "validity_status", length = 255)
    private String validityStatus;

    @Column(name = "embedding_status", nullable = false, length = 32)
    private String embeddingStatus = "PENDING";

    @Column(name = "indexed_at")
    private OffsetDateTime indexedAt;

    @CreationTimestamp
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getTitle() { return title; }
    public void setTitle(String title) { this.title = title; }
    public String getDocumentNumber() { return documentNumber; }
    public void setDocumentNumber(String documentNumber) { this.documentNumber = documentNumber; }
    public LocalDate getIssuedDate() { return issuedDate; }
    public void setIssuedDate(LocalDate issuedDate) { this.issuedDate = issuedDate; }
    public String getDocumentType() { return documentType; }
    public void setDocumentType(String documentType) { this.documentType = documentType; }
    public LocalDate getEffectiveDate() { return effectiveDate; }
    public void setEffectiveDate(LocalDate effectiveDate) { this.effectiveDate = effectiveDate; }
    public LocalDate getExpiredDate() { return expiredDate; }
    public void setExpiredDate(LocalDate expiredDate) { this.expiredDate = expiredDate; }
    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getGazetteDateRaw() { return gazetteDateRaw; }
    public void setGazetteDateRaw(String gazetteDateRaw) { this.gazetteDateRaw = gazetteDateRaw; }
    public String getSector() { return sector; }
    public void setSector(String sector) { this.sector = sector; }
    public String getField() { return field; }
    public void setField(String field) { this.field = field; }
    public String getIssuingAuthority() { return issuingAuthority; }
    public void setIssuingAuthority(String issuingAuthority) { this.issuingAuthority = issuingAuthority; }
    public String getSignerTitle() { return signerTitle; }
    public void setSignerTitle(String signerTitle) { this.signerTitle = signerTitle; }
    public String getSignerName() { return signerName; }
    public void setSignerName(String signerName) { this.signerName = signerName; }
    public String getScope() { return scope; }
    public void setScope(String scope) { this.scope = scope; }
    public Double getApplicationInfo() { return applicationInfo; }
    public void setApplicationInfo(Double applicationInfo) { this.applicationInfo = applicationInfo; }
    public String getValidityStatus() { return validityStatus; }
    public void setValidityStatus(String validityStatus) { this.validityStatus = validityStatus; }
    public String getEmbeddingStatus() { return embeddingStatus; }
    public void setEmbeddingStatus(String embeddingStatus) { this.embeddingStatus = embeddingStatus; }
    public OffsetDateTime getIndexedAt() { return indexedAt; }
    public void setIndexedAt(OffsetDateTime indexedAt) { this.indexedAt = indexedAt; }
}
