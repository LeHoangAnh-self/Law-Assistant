# Prepared Data (`data_usable`)

This folder contains ready-to-use data tables for local Law Assistant runs.

## Layout

```text
data_usable/
├── current_new/   # Current importer input for law-service
├── current/       # Legacy importer path (kept for compatibility)
├── rag/           # RAG-ready document/chunk/relationship tables
└── audit/         # Data quality report and flagged records
```

## Law Service Import Input

Use `current_new/`:

```text
current_new/metadata.parquet
current_new/context.parquet
current_new/relationships.parquet
current_new/anchors.parquet
```

`law-service` import endpoint still expects `metadata.parquet`, `content.parquet`, `relationships.parquet` in the source directory. Keep this in sync with importer expectations before changing paths.

## RAG Input

Use `rag/` tables for retrieval/indexing:

```text
rag/law_documents.parquet
rag/law_chunks.parquet
rag/law_relationships.parquet
```

## Audit Files

```text
audit/data_quality_report.json
audit/bad_documents.csv
```

Review `bad_documents.csv` if you need strict completeness.
