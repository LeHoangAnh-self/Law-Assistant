package com.lawassistant.lawservice.document;

import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface LegalDocumentRepository extends JpaRepository<LegalDocument, Long> {

    @Query("select d.id from LegalDocument d order by d.id")
    List<Long> findAllIds();

    @Modifying
    @Query("""
            update LegalDocument d
            set d.embeddingStatus = :status,
                d.indexedAt = case when :status = 'INDEXED' then current_timestamp else d.indexedAt end
            where d.id = :id
            """)
    int updateEmbeddingStatus(@Param("id") Long id, @Param("status") String status);

    @Query("""
            select d from LegalDocument d
            where (:query is null
                or lower(d.title) like lower(concat('%', :query, '%'))
                or lower(d.documentNumber) like lower(concat('%', :query, '%')))
              and (:documentType is null or d.documentType = :documentType)
              and (:validityStatus is null or d.validityStatus = :validityStatus)
              and (:scope is null or lower(d.scope) like lower(concat('%', :scope, '%')))
              and (:issuingAuthority is null or lower(d.issuingAuthority) like lower(concat('%', :issuingAuthority, '%')))
              and (:externalDocid is null or d.externalDocid = :externalDocid)
              and (:issuedDateFrom is null or d.issuedDate >= :issuedDateFrom)
              and (:issuedDateTo is null or d.issuedDate <= :issuedDateTo)
              and (:effectiveDateFrom is null or d.effectiveDate >= :effectiveDateFrom)
              and (:effectiveDateTo is null or d.effectiveDate <= :effectiveDateTo)
              and (:expiredDateFrom is null or d.expiredDate >= :expiredDateFrom)
              and (:expiredDateTo is null or d.expiredDate <= :expiredDateTo)
            """)
    Page<LegalDocument> search(
            @Param("query") String query,
            @Param("documentType") String documentType,
            @Param("validityStatus") String validityStatus,
            @Param("scope") String scope,
            @Param("issuingAuthority") String issuingAuthority,
            @Param("externalDocid") String externalDocid,
            @Param("issuedDateFrom") LocalDate issuedDateFrom,
            @Param("issuedDateTo") LocalDate issuedDateTo,
            @Param("effectiveDateFrom") LocalDate effectiveDateFrom,
            @Param("effectiveDateTo") LocalDate effectiveDateTo,
            @Param("expiredDateFrom") LocalDate expiredDateFrom,
            @Param("expiredDateTo") LocalDate expiredDateTo,
            Pageable pageable);
}
