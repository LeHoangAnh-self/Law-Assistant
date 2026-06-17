package com.lawassistant.lawservice.document;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface LegalDocumentRepository extends JpaRepository<LegalDocument, Long> {

    @Query("""
            select d from LegalDocument d
            where (:query is null
                or lower(d.title) like lower(concat('%', :query, '%'))
                or lower(d.documentNumber) like lower(concat('%', :query, '%')))
              and (:documentType is null or d.documentType = :documentType)
              and (:validityStatus is null or d.validityStatus = :validityStatus)
            """)
    Page<LegalDocument> search(
            @Param("query") String query,
            @Param("documentType") String documentType,
            @Param("validityStatus") String validityStatus,
            Pageable pageable);
}
