# Vietnamese Legal Documents Dataset

Dataset này là corpus văn bản pháp luật Việt Nam dùng cho:

- `law-service`: import metadata, nội dung và quan hệ văn bản vào MySQL.
- `rag-service`: tạo chunk, index vector và trả lời có nguồn tham chiếu.

Dữ liệu runnable hiện vẫn nằm ở root `data_usable/` để giữ tương thích với service command. Thư mục này chứa workspace tạo mới/tái tạo dataset và tài liệu đi kèm.

## Cấu Trúc

```text
vietnamese_legal_documents/
├── data_raw/      # Source capture nếu cần lưu để audit
├── data_usable/   # Artifact sạch khi chuyển runtime vào dataset folder
└── creation/
    ├── crawler/                         # Crawler VBPL/TVPL và exporter Parquet
    ├── prepare_law_assistant_dataset.py # Script chuẩn bị dataset legacy/RAG
    └── README.md
```

## Dataset Contract

### Import cho `law-service`

Path tương thích hiện tại:

```text
data_usable/current_new/
```

Các file chính:

- `metadata.parquet`: metadata văn bản và version hiện hành.
- `context.parquet`: nội dung theo cấp `DOCUMENT`, `ARTICLE`, `CLAUSE`, `POINT`, `TABLE`, `FORM`, `ANNEX`.
- `relationships.parquet`: quan hệ giữa văn bản.
- `anchors.parquet`: anchor ổn định để citation/RAG trỏ về đúng vị trí.

`law-service` importer hiện nhận được cả `content.parquet` hoặc `context.parquet`. Bộ `current_new` dùng `context.parquet`; importer tự lấy dòng `context_type = DOCUMENT` để nhập nội dung cấp văn bản.

### Input cho `rag-service`

Path tương thích hiện tại:

```text
data_usable/rag/
```

Các file chính:

- `law_documents.parquet`: một dòng mỗi văn bản với metadata, text và relationship summary.
- `law_chunks.parquet`: chunk truy xuất có `retrieval_text` đã ghép context pháp luật.
- `law_relationships.parquet`: graph quan hệ văn bản đã chuẩn hóa.

## Crawler Và Builder

Crawler mới nằm tại:

```text
creation/crawler/
```

Crawler dùng để lấy dữ liệu trực tiếp từ VBPL/Thư Viện Pháp Luật, parse cấu trúc điều/khoản/điểm, xử lý PDF và export Parquet. Xem [crawler README](creation/crawler/README.md) để biết tiêu chí crawl, fallback, OCR và quality workaround.

Script `prepare_law_assistant_dataset.py` là pipeline chuẩn bị dữ liệu legacy/RAG từ các source Parquet đã có. Nó vẫn hữu ích khi cần tạo lại bảng `rag/` từ dữ liệu văn bản đã export.

## Tiêu Chí Chất Lượng Chính

- Mỗi document cần có ID ổn định để dedupe, retry và join.
- Metadata và content cấp document phải join được với nhau.
- Relationship không được self-link và nên được dedupe trước khi dùng cho RAG.
- Context nên giữ được cấp trích dẫn nhỏ nhất có thể: điều, khoản, điểm, bảng, biểu mẫu, phụ lục.
- PDF-only document chất lượng thấp không được đưa thẳng vào RAG nếu chưa review/OCR đạt yêu cầu.
- Generated answer trong RAG phải trích nguồn từ context/anchor, không chỉ trích tên văn bản chung chung.

## Ghi Chú Tương Thích

Nếu chuyển prepared dataset từ root `data_usable/` vào `dataset/vietnamese_legal_documents/data_usable/`, cần cập nhật:

- root `README.md`;
- `law-service/README.md`;
- `rag-service/README.md`;
- mọi command dùng `sourceDirectory`;
- script hoặc test đang hardcode `data_usable/`.
