# Prepared Dataset

This folder contains the final cleaned dataset for Law Assistant.

## Folder Layout

```text
data_usable/
├── current/   # Importer-compatible data for law-service
├── rag/       # RAG-ready document, relationship, and chunk tables
└── audit/     # Data quality report and records that need review
```

## Import Data

Use `current/` when importing into `law-service`:

```text
current/metadata.parquet
current/content.parquet
current/relationships.parquet
```

Import command:

```bash
cd ../law-service
curl -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current"
```

Expected rows:

```json
{
  "metadataRows": 127267,
  "contentRows": 127267,
  "relationshipRows": 651966
}
```

## RAG Data

Use `rag/` for embeddings, retrieval, and offline analysis:

```text
rag/law_documents.parquet
rag/law_chunks.parquet
rag/law_relationships.parquet
```

`law_chunks.parquet` is the main embedding input. Use:

- `retrieval_text`: document metadata context plus the chunk text
- `chunk_text`: raw extracted legal passage
- `document_id`, `chunk_id`, `chunk_index`: stable identifiers
- `title`, `so_ky_hieu`, `loai_van_ban`, `tinh_trang_hieu_luc`, dates, authority, scope, sector, and field as payload metadata

Default chunking:

- Chunk size: `1,500` characters
- Overlap: `200` characters
- Total chunks: `1,203,686`

## Quality Summary

- Documents: `127,267`
- Cleaned relationships: `651,966`
- Duplicate relationship rows removed: `5,685`
- Self-links removed: `268`
- Documents with empty extracted text: `1`
- Documents with extracted text shorter than 80 characters: `89`

Detailed audit files:

```text
audit/data_quality_report.json
audit/bad_documents.csv
```

Review `bad_documents.csv` before production use if complete coverage is required.

## GitHub Note

These Parquet files are large and should be committed with Git LFS. The repository root includes `.gitattributes` for `*.parquet`.
