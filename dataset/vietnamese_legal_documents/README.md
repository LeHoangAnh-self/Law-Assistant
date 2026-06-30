# Vietnamese Legal Documents Dataset

Prepared legal-document data for `law-service` imports and `rag-service` indexing.

The existing prepared dataset currently remains at root `data_usable/` to preserve service compatibility. Future regenerated data can be written under this dataset folder after the service commands are migrated.

## Folders

```text
vietnamese_legal_documents/
├── data_raw/      # Source Parquet exports such as metadata/content/relationships
├── data_usable/   # Prepared current/, rag/, and audit/ outputs
└── creation/      # Preparation notes and audit reports
```

## Current Compatibility Path

Existing importer commands still use:

```text
data_usable/current
```

If the prepared dataset is moved here, update:

- root `README.md`
- `law-service/README.md`
- any scripts or tests that reference `data_usable/current`
- operational import commands using `sourceDirectory`
