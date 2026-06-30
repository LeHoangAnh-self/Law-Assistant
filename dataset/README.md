# Dataset Workspace

Canonical dataset workspace for Law Assistant.

## Layout

```text
dataset/
├── vietnamese_legal_documents/
│   ├── data_raw/
│   ├── data_usable/
│   └── creation/
└── baochinhphu_official_qa/
    ├── data_raw/
    ├── data_usable/
    └── creation/
```

## Conventions

- Keep `data_raw/` immutable source captures.
- Put cleaned/exportable artifacts in `data_usable/`.
- Put scripts, notebooks, and docs in `creation/`.

## Notes

- The running services currently use root `data_usable/` paths for compatibility.
- If you switch services to `dataset/.../data_usable`, update README commands and import scripts in the same commit.
