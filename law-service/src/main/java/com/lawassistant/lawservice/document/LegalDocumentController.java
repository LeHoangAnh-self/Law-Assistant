package com.lawassistant.lawservice.document;

import com.lawassistant.lawservice.embedding.EmbeddingEventPublisher;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/documents")
public class LegalDocumentController {

    private final LegalDocumentService documentService;
    private final EmbeddingEventPublisher embeddingEventPublisher;

    public LegalDocumentController(LegalDocumentService documentService, EmbeddingEventPublisher embeddingEventPublisher) {
        this.documentService = documentService;
        this.embeddingEventPublisher = embeddingEventPublisher;
    }

    @GetMapping
    public Page<LegalDocument> search(
            @RequestParam(required = false) String query,
            @RequestParam(required = false) String documentType,
            @RequestParam(required = false) String validityStatus,
            @RequestParam(required = false) String scope,
            @RequestParam(required = false) String issuingAuthority,
            @RequestParam(required = false) String externalDocid,
            @RequestParam(required = false) LocalDate issuedDateFrom,
            @RequestParam(required = false) LocalDate issuedDateTo,
            @RequestParam(required = false) LocalDate effectiveDateFrom,
            @RequestParam(required = false) LocalDate effectiveDateTo,
            @RequestParam(required = false) LocalDate expiredDateFrom,
            @RequestParam(required = false) LocalDate expiredDateTo,
            @RequestParam(defaultValue = "0") @Min(0) int page,
            @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
        return documentService.search(
                query,
                documentType,
                validityStatus,
                scope,
                issuingAuthority,
                externalDocid,
                issuedDateFrom,
                issuedDateTo,
                effectiveDateFrom,
                effectiveDateTo,
                expiredDateFrom,
                expiredDateTo,
                PageRequest.of(page, size, Sort.by(Sort.Direction.DESC, "issuedDate").and(Sort.by("id"))));
    }

    @GetMapping("/ids")
    public List<Long> findAllIds() {
        return documentService.findAllDocumentIds();
    }

    @GetMapping("/{id}")
    public LegalDocumentDetail getDetail(@PathVariable Long id) {
        return documentService.getDetail(id);
    }

    @PostMapping("/{id}/embedding-events")
    public void requestEmbeddingUpdate(@PathVariable Long id) {
        embeddingEventPublisher.publishDocumentUpdated(id);
    }

    @PostMapping("/embedding-events")
    public int requestEmbeddingUpdates() {
        List<Long> ids = documentService.findAllDocumentIds();
        ids.forEach(embeddingEventPublisher::publishDocumentUpdated);
        return ids.size();
    }
}
