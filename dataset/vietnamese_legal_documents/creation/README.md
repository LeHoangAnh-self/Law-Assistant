# Dataset Creation

Thư mục này chứa code tạo và tái tạo dataset văn bản pháp luật Việt Nam.

## Thành Phần

```text
creation/
├── crawler/                         # Crawler VBPL/TVPL, parser, exporter, tests
├── prepare_law_assistant_dataset.py # Builder legacy/RAG từ Parquet source
└── README.md
```

## Crawler Pipeline

Crawler nằm trong [crawler/](crawler/README.md). Đây là pipeline đầy đủ để:

- discover URL văn bản từ VBPL sitemap hoặc seed file;
- fetch nội dung qua VBPL API;
- fallback sang Thư Viện Pháp Luật khi cần;
- parse cấu trúc điều/khoản/điểm/bảng/phụ lục;
- xử lý PDF text/OCR/review;
- export Parquet cho `law-service`.

Chạy từ root repo:

```bash
cd dataset/vietnamese_legal_documents/creation/crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d law-crawler-mysql
vn-law-crawler init-db
```

Export sang path tương thích hiện tại:

```bash
vn-law-crawler export-parquet --output-dir ../../../../data_usable/current_new
```

## Legacy/RAG Preparation Pipeline

Script hiện có:

```bash
python3 dataset/vietnamese_legal_documents/creation/prepare_law_assistant_dataset.py \
  --input-dir data \
  --output-dir dataset/vietnamese_legal_documents/data_usable
```

Script này dùng khi đã có source Parquet đầu vào và cần tạo artifact importer/RAG như `current/`, `rag/`, audit report.

## Ghi Chú

Root `data_usable/` vẫn là compatibility path cho service runtime hiện tại. Nếu chuyển runtime sang `dataset/vietnamese_legal_documents/data_usable/`, cập nhật README, command import và test trong cùng commit.
