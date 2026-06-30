# Dataset Workspace

Thư mục này là workspace dataset chính cho Law Assistant. Nó chứa dữ liệu nguồn, dữ liệu đã làm sạch, script tạo dataset và crawler dùng để tái tạo corpus văn bản pháp luật Việt Nam.

## Cấu Trúc

```text
dataset/
├── vietnamese_legal_documents/
│   ├── data_raw/
│   ├── data_usable/
│   └── creation/
│       ├── crawler/                         # Crawler VBPL/TVPL và exporter Parquet
│       └── prepare_law_assistant_dataset.py # Script chuẩn bị dataset legacy/RAG
└── baochinhphu_official_qa/
    ├── data_raw/
    ├── data_usable/
    └── creation/
```

## Dataset Chính

- `vietnamese_legal_documents`: corpus văn bản pháp luật Việt Nam dùng cho `law-service` import và `rag-service` indexing.
- `baochinhphu_official_qa`: bộ Q&A chính thức từ Báo Chính phủ dùng cho evaluation, không phải corpus văn bản pháp luật độc lập.

## Quy Ước

- `data_raw/`: lưu source capture bất biến nếu cần audit.
- `data_usable/`: lưu artifact sạch, có thể export hoặc dùng trong test/evaluation.
- `creation/`: lưu crawler, builder, script migration, audit note và tài liệu tái tạo dataset.

## Crawler Văn Bản Pháp Luật

Crawler đã được đưa vào:

```text
dataset/vietnamese_legal_documents/creation/crawler/
```

Crawler này:

- phát hiện URL VBPL từ sitemap hoặc seed file;
- chỉ nhận URL có `document_id` rõ ràng;
- fetch nội dung qua VBPL API trước;
- fallback sang Thư Viện Pháp Luật khi VBPL API lỗi hoặc thiếu content;
- xử lý PDF-only document bằng PDF text/OCR/review queue;
- parse văn bản thành `DOCUMENT`, `ARTICLE`, `CLAUSE`, `POINT`, `TABLE`, `FORM`, `ANNEX`;
- export `metadata.parquet`, `context.parquet`, `relationships.parquet`, `anchors.parquet`, `pdf_review.parquet`.

Chi tiết tiêu chí crawl và workaround nằm trong [crawler README](vietnamese_legal_documents/creation/crawler/README.md).

## Ghi Chú Tương Thích

Các service đang chạy hiện vẫn dùng path root `data_usable/` để giữ tương thích với README và command hiện tại.

Nếu chuyển runtime sang `dataset/.../data_usable`, cần cập nhật cùng lúc:

- root `README.md`;
- `law-service/README.md`;
- `rag-service/README.md`;
- import command có `sourceDirectory`;
- script/test đang tham chiếu root `data_usable/`.
