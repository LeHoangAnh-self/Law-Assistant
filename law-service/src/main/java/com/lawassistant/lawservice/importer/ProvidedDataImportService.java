package com.lawassistant.lawservice.importer;

import com.lawassistant.lawservice.embedding.EmbeddingEventPublisher;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Date;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.apache.avro.Schema;
import org.apache.avro.SchemaBuilder;
import org.apache.avro.generic.GenericRecord;
import org.apache.parquet.avro.AvroParquetReader;
import org.apache.parquet.avro.AvroReadSupport;
import org.apache.parquet.io.LocalInputFile;
import org.apache.hadoop.conf.Configuration;
import org.jsoup.Jsoup;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class ProvidedDataImportService {

    private static final int BATCH_SIZE = 5_000;
    private static final int CONTENT_BATCH_SIZE = 20;
    private static final DateTimeFormatter VIETNAMESE_DATE = DateTimeFormatter.ofPattern("dd/MM/yyyy");
    private static final Pattern EXTERNAL_DOCID_PATTERN = Pattern.compile("(?:docid|document_id)=([0-9]+)");
    private static final Pattern TRAILING_EXTERNAL_DOCID_PATTERN = Pattern.compile("--([0-9]+)(?:$|[?#])");
    private static final Schema CONTEXT_CONTENT_PROJECTION = SchemaBuilder
            .record("context_content_projection")
            .fields()
            .optionalLong("id")
            .optionalLong("document_id")
            .optionalString("context_type")
            .optionalString("content_text")
            .optionalString("text")
            .optionalString("content_html")
            .optionalString("html")
            .optionalString("content")
            .endRecord();

    private final JdbcTemplate jdbcTemplate;
    private final EmbeddingEventPublisher embeddingEventPublisher;
    private final CacheManager cacheManager;

    public ProvidedDataImportService(
            JdbcTemplate jdbcTemplate,
            EmbeddingEventPublisher embeddingEventPublisher,
            CacheManager cacheManager) {
        this.jdbcTemplate = jdbcTemplate;
        this.embeddingEventPublisher = embeddingEventPublisher;
        this.cacheManager = cacheManager;
    }

    @Transactional(rollbackFor = IOException.class)
    public ProvidedDataImportResult importFrom(Path dataDirectory, boolean publishEmbeddingEvents) throws IOException {
        Path metadata = requiredFile(dataDirectory, "metadata.parquet");
        Path content = optionalFile(dataDirectory, "content.parquet");
        Path context = optionalFile(dataDirectory, "context.parquet");
        Path relationships = requiredFile(dataDirectory, "relationships.parquet");
        if (content == null && context == null) {
            throw new IOException("Required data file not found: " + dataDirectory.resolve("content.parquet")
                    + " or " + dataDirectory.resolve("context.parquet"));
        }

        ImportRows metadataRows = importMetadata(metadata);
        long contentRows = content == null ? importContentFromContext(context) : importContent(content);
        long relationshipRows = importRelationships(relationships, metadataRows.documentIds());
        evictDocumentDetailCache(metadataRows.documentIds());

        if (publishEmbeddingEvents) {
            publishEmbeddingEventsAfterCommit(metadataRows.documentIds());
        }

        return new ProvidedDataImportResult(
                metadataRows.rowCount(),
                contentRows,
                relationshipRows,
                publishEmbeddingEvents);
    }

    private ImportRows importMetadata(Path parquetFile) throws IOException {
        String sql = """
                insert into legal_documents (
                    id, external_source, external_docid, title, document_number, issued_date,
                    document_type, effective_date, expired_date, source, source_url, gazette_date_raw,
                    sector, field, issuing_authority, signer_title, signer_name, scope,
                    application_info, validity_status, embedding_status
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                on duplicate key update
                    external_source = values(external_source),
                    external_docid = values(external_docid),
                    title = values(title),
                    document_number = values(document_number),
                    issued_date = values(issued_date),
                    document_type = values(document_type),
                    effective_date = values(effective_date),
                    expired_date = values(expired_date),
                    source = values(source),
                    source_url = values(source_url),
                    gazette_date_raw = values(gazette_date_raw),
                    sector = values(sector),
                    field = values(field),
                    issuing_authority = values(issuing_authority),
                    signer_title = values(signer_title),
                    signer_name = values(signer_name),
                    scope = values(scope),
                    application_info = values(application_info),
                    validity_status = values(validity_status),
                    embedding_status = 'PENDING',
                    indexed_at = null,
                    updated_at = current_timestamp(6)
                """;

        List<Object[]> batch = new ArrayList<>(BATCH_SIZE);
        Set<Long> documentIds = new LinkedHashSet<>();
        long rows = 0;
        try (var reader = parquetReader(parquetFile)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                Long id = firstLong(record, "id", "document_id");
                String sourceUrl = firstText(record, "source_url", "url", "vanban_url");
                String source = text(record, "nguon_thu_thap");
                if (source == null) {
                    source = text(record, "source");
                }
                if (sourceUrl == null && source != null && source.startsWith("http")) {
                    sourceUrl = source;
                }
                String externalDocid = firstText(record, "external_docid", "docid", "document_id_external");
                if (externalDocid == null) {
                    externalDocid = extractExternalDocid(sourceUrl);
                }
                String externalSource = firstText(record, "external_source", "source_system", "external_host");
                if (externalSource == null && externalDocid != null) {
                    externalSource = extractExternalSource(sourceUrl);
                }
                batch.add(new Object[] {
                        id,
                        externalSource,
                        externalDocid,
                        text(record, "title"),
                        firstText(record, "so_ky_hieu", "document_number"),
                        sqlDate(record, "ngay_ban_hanh", "issued_date"),
                        firstText(record, "loai_van_ban", "document_type"),
                        sqlDate(record, "ngay_co_hieu_luc", "effective_date"),
                        sqlDate(record, "ngay_het_hieu_luc", "expired_date"),
                        source,
                        sourceUrl,
                        text(record, "ngay_dang_cong_bao"),
                        text(record, "nganh"),
                        text(record, "linh_vuc"),
                        firstText(record, "co_quan_ban_hanh", "issuing_authority"),
                        text(record, "chuc_danh"),
                        text(record, "nguoi_ky"),
                        text(record, "pham_vi"),
                        doubleValue(record, "thong_tin_ap_dung"),
                        firstText(record, "tinh_trang_hieu_luc", "validity_status")
                });
                rows++;
                if (id != null) {
                    documentIds.add(id);
                }
                if (batch.size() == BATCH_SIZE) {
                    jdbcTemplate.batchUpdate(sql, batch);
                    batch.clear();
                }
            }
        }
        if (!batch.isEmpty()) {
            jdbcTemplate.batchUpdate(sql, batch);
        }
        return new ImportRows(rows, documentIds);
    }

    private long importContent(Path parquetFile) throws IOException {
        String sql = """
                insert into legal_document_contents (document_id, content_html, content_text)
                values (?, ?, ?)
                on duplicate key update
                    content_html = values(content_html),
                    content_text = values(content_text),
                    updated_at = current_timestamp(6)
                """;

        List<Object[]> batch = new ArrayList<>(CONTENT_BATCH_SIZE);
        long rows = 0;
        try (var reader = parquetReader(parquetFile, CONTEXT_CONTENT_PROJECTION)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                Long id = firstLong(record, "id", "document_id");
                String html = firstText(record, "content_html", "html", "content");
                String contentText = firstText(record, "content_text", "text");
                if (html == null) {
                    html = contentText == null ? "" : contentText;
                }
                if (contentText == null) {
                    contentText = Jsoup.parse(html).text();
                }
                batch.add(new Object[] {id, html, contentText});
                rows++;
                if (batch.size() == CONTENT_BATCH_SIZE) {
                    jdbcTemplate.batchUpdate(sql, batch);
                    batch.clear();
                }
            }
        }
        if (!batch.isEmpty()) {
            jdbcTemplate.batchUpdate(sql, batch);
        }
        return rows;
    }

    private long importContentFromContext(Path parquetFile) throws IOException {
        String sql = """
                insert into legal_document_contents (document_id, content_html, content_text)
                values (?, ?, ?)
                on duplicate key update
                    content_html = values(content_html),
                    content_text = values(content_text),
                    updated_at = current_timestamp(6)
                """;

        List<Object[]> batch = new ArrayList<>(CONTENT_BATCH_SIZE);
        long rows = 0;
        try (var reader = parquetReader(parquetFile)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                String contextType = text(record, "context_type");
                if (!"DOCUMENT".equals(contextType)) {
                    continue;
                }
                Long id = longValue(record, "document_id");
                String contentText = text(record, "content_text");
                String html = text(record, "content_html");
                if (html == null) {
                    html = contentText == null ? "" : contentText;
                }
                if (contentText == null) {
                    contentText = Jsoup.parse(html).text();
                }
                batch.add(new Object[] {id, html, contentText});
                rows++;
                if (batch.size() == CONTENT_BATCH_SIZE) {
                    jdbcTemplate.batchUpdate(sql, batch);
                    batch.clear();
                }
            }
        }
        if (!batch.isEmpty()) {
            jdbcTemplate.batchUpdate(sql, batch);
        }
        return rows;
    }

    private long importRelationships(Path parquetFile, Set<Long> importedDocumentIds) throws IOException {
        String deleteSql = "delete from legal_document_relationships where document_id = ?";
        String insertSql = """
                insert into legal_document_relationships
                    (document_id, related_document_id, relationship_type)
                values (?, ?, ?)
                """;

        List<Object[]> relationshipBatch = new ArrayList<>(BATCH_SIZE);
        long rows = 0;
        try (var reader = parquetReader(parquetFile)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                Long documentId = firstLong(record, "doc_id", "document_id");
                relationshipBatch.add(new Object[] {
                        documentId,
                        firstLong(record, "other_doc_id", "related_document_id"),
                        firstText(record, "relationship", "relationship_type")
                });
                rows++;
            }
        }
        List<Object[]> deleteBatch = importedDocumentIds.stream()
                .filter(id -> id != null)
                .map(id -> new Object[] {id})
                .toList();
        if (!deleteBatch.isEmpty()) {
            jdbcTemplate.batchUpdate(deleteSql, deleteBatch);
        }
        for (List<Object[]> batch : batches(relationshipBatch, BATCH_SIZE)) {
            jdbcTemplate.batchUpdate(insertSql, batch);
        }
        return rows;
    }

    private void evictDocumentDetailCache(Set<Long> documentIds) {
        var cache = cacheManager.getCache("legal-document-detail");
        if (cache == null) {
            return;
        }
        documentIds.forEach(cache::evict);
    }

    private void publishEmbeddingEventsAfterCommit(Set<Long> documentIds) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) {
            documentIds.forEach(embeddingEventPublisher::publishDocumentUpdated);
            return;
        }
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                documentIds.forEach(embeddingEventPublisher::publishDocumentUpdated);
            }
        });
    }

    private static List<List<Object[]>> batches(List<Object[]> rows, int batchSize) {
        List<List<Object[]>> batches = new ArrayList<>();
        for (int index = 0; index < rows.size(); index += batchSize) {
            batches.add(rows.subList(index, Math.min(index + batchSize, rows.size())));
        }
        return batches;
    }

    private static Path optionalFile(Path directory, String name) {
        Path file = directory.resolve(name).normalize();
        return Files.isRegularFile(file) ? file : null;
    }

    private static Path requiredFile(Path directory, String name) throws IOException {
        Path file = directory.resolve(name).normalize();
        if (!Files.isRegularFile(file)) {
            throw new IOException("Required data file not found: " + file);
        }
        return file;
    }

    private static org.apache.parquet.hadoop.ParquetReader<GenericRecord> parquetReader(Path parquetFile) throws IOException {
        return AvroParquetReader.<GenericRecord>builder(new LocalInputFile(parquetFile)).build();
    }

    private static org.apache.parquet.hadoop.ParquetReader<GenericRecord> parquetReader(
            Path parquetFile,
            Schema requestedProjection) throws IOException {
        Configuration configuration = new Configuration();
        AvroReadSupport.setRequestedProjection(configuration, requestedProjection);
        AvroReadSupport.setAvroReadSchema(configuration, requestedProjection);
        return AvroParquetReader.<GenericRecord>builder(new LocalInputFile(parquetFile))
                .withConf(configuration)
                .build();
    }

    private static String text(GenericRecord record, String field) {
        if (!hasField(record, field)) {
            return null;
        }
        Object value = record.get(field);
        return value == null ? null : value.toString();
    }

    private static String firstText(GenericRecord record, String... fields) {
        for (String field : fields) {
            if (record.getSchema().getField(field) == null) {
                continue;
            }
            String value = text(record, field);
            if (value != null && !value.isBlank()) {
                return value;
            }
        }
        return null;
    }

    private static boolean hasField(GenericRecord record, String field) {
        Schema schema = record.getSchema();
        return schema != null && schema.getField(field) != null;
    }

    private static String extractExternalDocid(String sourceUrl) {
        if (sourceUrl == null || sourceUrl.isBlank()) {
            return null;
        }
        Matcher matcher = EXTERNAL_DOCID_PATTERN.matcher(sourceUrl);
        if (matcher.find()) {
            return matcher.group(1);
        }
        matcher = TRAILING_EXTERNAL_DOCID_PATTERN.matcher(sourceUrl);
        return matcher.find() ? matcher.group(1) : null;
    }

    private static String extractExternalSource(String sourceUrl) {
        if (sourceUrl == null || sourceUrl.isBlank()) {
            return null;
        }
        if (sourceUrl.contains("vanban.chinhphu.vn")) {
            return "vanban.chinhphu.vn";
        }
        if (sourceUrl.contains("vbpl.vn")) {
            return "vbpl.vn";
        }
        return null;
    }

    private static Long longValue(GenericRecord record, String field) {
        if (!hasField(record, field)) {
            return null;
        }
        Object value = record.get(field);
        return value instanceof Number number ? number.longValue() : parseLong(value == null ? null : value.toString());
    }

    private static Long firstLong(GenericRecord record, String... fields) {
        for (String field : fields) {
            Long value = longValue(record, field);
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private static Double doubleValue(GenericRecord record, String field) {
        if (!hasField(record, field)) {
            return null;
        }
        Object value = record.get(field);
        return value instanceof Number number ? number.doubleValue() : null;
    }

    private static Date sqlDate(GenericRecord record, String... fields) {
        for (String field : fields) {
            if (!hasField(record, field)) {
                continue;
            }
            Date date = sqlDateValue(record.get(field));
            if (date != null) {
                return date;
            }
        }
        return null;
    }

    private static Date sqlDateValue(Object rawValue) {
        if (rawValue == null) {
            return null;
        }
        if (rawValue instanceof LocalDate localDate) {
            return Date.valueOf(localDate);
        }
        if (rawValue instanceof Number daysSinceEpoch) {
            return Date.valueOf(LocalDate.ofEpochDay(daysSinceEpoch.longValue()));
        }
        String value = rawValue.toString();
        if (value == null || value.isBlank() || value.equals("...")) {
            return null;
        }
        try {
            return Date.valueOf(LocalDate.parse(value, VIETNAMESE_DATE));
        } catch (DateTimeParseException ignored) {
            try {
                return Date.valueOf(LocalDate.parse(value));
            } catch (DateTimeParseException ignoredAgain) {
                return null;
            }
        }
    }

    private static Long parseLong(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return Long.parseLong(value);
    }

    private record ImportRows(long rowCount, Set<Long> documentIds) {
    }
}
