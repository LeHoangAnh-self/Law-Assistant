package com.lawassistant.lawservice.document;

import com.lawassistant.lawservice.relationship.LegalDocumentRelationshipRepository;
import jakarta.persistence.EntityNotFoundException;
import java.time.LocalDate;
import java.util.List;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

@Service
public class LegalDocumentService {

    private final LegalDocumentRepository documentRepository;
    private final LegalDocumentContentRepository contentRepository;
    private final LegalDocumentRelationshipRepository relationshipRepository;

    public LegalDocumentService(
            LegalDocumentRepository documentRepository,
            LegalDocumentContentRepository contentRepository,
            LegalDocumentRelationshipRepository relationshipRepository) {
        this.documentRepository = documentRepository;
        this.contentRepository = contentRepository;
        this.relationshipRepository = relationshipRepository;
    }

    @Transactional(readOnly = true)
    public Page<LegalDocument> search(
            String query,
            String documentType,
            String validityStatus,
            String scope,
            String issuingAuthority,
            String externalDocid,
            LocalDate issuedDateFrom,
            LocalDate issuedDateTo,
            LocalDate effectiveDateFrom,
            LocalDate effectiveDateTo,
            LocalDate expiredDateFrom,
            LocalDate expiredDateTo,
            Pageable pageable) {
        return documentRepository.search(
                blankToNull(query),
                blankToNull(documentType),
                blankToNull(validityStatus),
                blankToNull(scope),
                blankToNull(issuingAuthority),
                blankToNull(externalDocid),
                issuedDateFrom,
                issuedDateTo,
                effectiveDateFrom,
                effectiveDateTo,
                expiredDateFrom,
                expiredDateTo,
                pageable);
    }

    @Cacheable(cacheNames = "legal-document-detail", key = "#id")
    @Transactional(readOnly = true)
    public LegalDocumentDetail getDetail(Long id) {
        LegalDocument document = documentRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("Legal document not found: " + id));
        LegalDocumentContent content = contentRepository.findById(id).orElse(null);
        return new LegalDocumentDetail(
                document,
                content == null ? null : content.getContentHtml(),
                content == null ? null : content.getContentText(),
                relationshipRepository.findByDocumentId(id));
    }

    @Transactional(readOnly = true)
    public List<Long> findAllDocumentIds() {
        return documentRepository.findAllIds();
    }

    @CacheEvict(cacheNames = "legal-document-detail", key = "#id")
    public void evictDetail(Long id) {
    }

    private static String blankToNull(String value) {
        return StringUtils.hasText(value) ? value : null;
    }
}
