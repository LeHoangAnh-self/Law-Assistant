# Dataset Creation Notes

Use this folder for legal-document preparation notes, quality reports, and migration plans.

Current preparation script:

```bash
python3 dataset/vietnamese_legal_documents/creation/prepare_law_assistant_dataset.py \
  --input-dir data \
  --output-dir dataset/vietnamese_legal_documents/data_usable
```

The root `data_usable/` path is still the compatibility location until service documentation and deployment scripts are migrated.
