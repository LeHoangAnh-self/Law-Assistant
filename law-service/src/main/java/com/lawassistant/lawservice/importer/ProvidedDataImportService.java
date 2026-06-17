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
import java.util.List;
import org.apache.avro.generic.GenericRecord;
import org.apache.parquet.avro.AvroParquetReader;
import org.apache.parquet.io.LocalInputFile;
import org.jsoup.Jsoup;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProvidedDataImportService {

    private static final int BATCH_SIZE = 1_000;
    private static final DateTimeFormatter VIETNAMESE_DATE = DateTimeFormatter.ofPattern("dd/MM/yyyy");

    private final JdbcTemplate jdbcTemplate;
    private final EmbeddingEventPublisher embeddingEventPublisher;

    public ProvidedDataImportService(JdbcTemplate jdbcTemplate, EmbeddingEventPublisher embeddingEventPublisher) {
        this.jdbcTemplate = jdbcTemplate;
        this.embeddingEventPublisher = embeddingEventPublisher;
    }

    public ProvidedDataImportResult importFrom(Path dataDirectory, boolean publishEmbeddingEvents) throws IOException {
        Path metadata = requiredFile(dataDirectory, "metadata.parquet");
        Path content = requiredFile(dataDirectory, "content.parquet");
        Path relationships = requiredFile(dataDirectory, "relationships.parquet");

        long metadataRows = importMetadata(metadata, publishEmbeddingEvents);
        long contentRows = importContent(content);
        long relationshipRows = importRelationships(relationships);

        return new ProvidedDataImportResult(metadataRows, contentRows, relationshipRows, publishEmbeddingEvents);
    }

    private long importMetadata(Path parquetFile, boolean publishEmbeddingEvents) throws IOException {
        String sql = """
                insert into legal_documents (
                    id, title, document_number, issued_date, document_type, effective_date, expired_date,
                    source, gazette_date_raw, sector, field, issuing_authority, signer_title, signer_name,
                    scope, application_info, validity_status, embedding_status
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
                on duplicate key update
                    title = values(title),
                    document_number = values(document_number),
                    issued_date = values(issued_date),
                    document_type = values(document_type),
                    effective_date = values(effective_date),
                    expired_date = values(expired_date),
                    source = values(source),
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
                    updated_at = current_timestamp(6)
                """;

        List<Object[]> batch = new ArrayList<>(BATCH_SIZE);
        long rows = 0;
        try (var reader = parquetReader(parquetFile)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                Long id = longValue(record, "id");
                batch.add(new Object[] {
                        id,
                        text(record, "title"),
                        text(record, "so_ky_hieu"),
                        sqlDate(record, "ngay_ban_hanh"),
                        text(record, "loai_van_ban"),
                        sqlDate(record, "ngay_co_hieu_luc"),
                        sqlDate(record, "ngay_het_hieu_luc"),
                        text(record, "nguon_thu_thap"),
                        text(record, "ngay_dang_cong_bao"),
                        text(record, "nganh"),
                        text(record, "linh_vuc"),
                        text(record, "co_quan_ban_hanh"),
                        text(record, "chuc_danh"),
                        text(record, "nguoi_ky"),
                        text(record, "pham_vi"),
                        doubleValue(record, "thong_tin_ap_dung"),
                        text(record, "tinh_trang_hieu_luc")
                });
                rows++;
                if (publishEmbeddingEvents && id != null) {
                    embeddingEventPublisher.publishDocumentUpdated(id);
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
        return rows;
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

        List<Object[]> batch = new ArrayList<>(BATCH_SIZE);
        long rows = 0;
        try (var reader = parquetReader(parquetFile)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                Long id = parseLong(text(record, "id"));
                String html = text(record, "content_html");
                batch.add(new Object[] {id, html, html == null ? null : Jsoup.parse(html).text()});
                rows++;
                if (batch.size() == BATCH_SIZE) {
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

    private long importRelationships(Path parquetFile) throws IOException {
        String sql = """
                insert ignore into legal_document_relationships
                    (document_id, related_document_id, relationship_type)
                values (?, ?, ?)
                """;

        List<Object[]> batch = new ArrayList<>(BATCH_SIZE);
        long rows = 0;
        try (var reader = parquetReader(parquetFile)) {
            GenericRecord record;
            while ((record = reader.read()) != null) {
                batch.add(new Object[] {
                        longValue(record, "doc_id"),
                        longValue(record, "other_doc_id"),
                        text(record, "relationship")
                });
                rows++;
                if (batch.size() == BATCH_SIZE) {
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

    private static String text(GenericRecord record, String field) {
        Object value = record.get(field);
        return value == null ? null : value.toString();
    }

    private static Long longValue(GenericRecord record, String field) {
        Object value = record.get(field);
        return value instanceof Number number ? number.longValue() : parseLong(value == null ? null : value.toString());
    }

    private static Double doubleValue(GenericRecord record, String field) {
        Object value = record.get(field);
        return value instanceof Number number ? number.doubleValue() : null;
    }

    private static Date sqlDate(GenericRecord record, String field) {
        String value = text(record, field);
        if (value == null || value.isBlank() || value.equals("...")) {
            return null;
        }
        try {
            return Date.valueOf(LocalDate.parse(value, VIETNAMESE_DATE));
        } catch (DateTimeParseException ignored) {
            return null;
        }
    }

    private static Long parseLong(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return Long.parseLong(value);
    }
}
