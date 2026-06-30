# VN Law Crawler

Đây là subproject crawler dùng để xây dựng dataset văn bản pháp luật Việt Nam cho Law Assistant. Code được chuyển từ workspace crawler độc lập vào repo này để có thể upload lên GitHub cùng phần dataset documentation.

Crawler ưu tiên giữ nguyên HTML/text toàn văn để audit, đồng thời tách cấu trúc pháp luật thành các bảng có thể dùng cho RAG: văn bản, phiên bản, điều, khoản, điểm, bảng, biểu mẫu, phụ lục, anchor ổn định và quan hệ giữa văn bản.

## Vị Trí Trong Repo

```text
dataset/vietnamese_legal_documents/creation/crawler/
├── src/law_crawler/      # Package crawler chính
├── scripts/              # Preview, validate export, resolve fallback URL
├── tests/                # Unit tests cho parser/fetcher/discovery/repository
├── sql/schema.sql        # Schema tham khảo
├── docker-compose.yml    # MySQL local cho crawler
├── pyproject.toml        # Python package config
└── .env.example          # Biến môi trường mẫu, không chứa secret thật
```

## Tiêu Chí Crawl

### Nguồn phát hiện URL

Discovery chỉ nhận URL có thể truy ra `document_id` rõ ràng:

- URL chi tiết mới của VBPL: `/van-ban/chi-tiet/...--{id}`
- URL toàn văn legacy của VBPL: `/Pages/vbpq-toanvan.aspx?...ItemID={id}`
- URL seed file cũng phải thỏa một trong hai dạng trên.

Các URL listing, chuyên mục, tag, search page hoặc URL không có document id bị bỏ qua. Cách này giúp dataset có khóa ổn định để merge, retry và export.

### Nguồn fetch nội dung

Thứ tự fetch hiện tại:

1. Public VBPL API: `qtdc/public/doc/{document_id}`.
2. Nếu API lỗi hoặc thiếu content, fallback sang `thuvienphapluat.vn` theo mapping thủ công hoặc search tự động.
3. Nếu văn bản chỉ có PDF, crawler thử extract text nhúng trong PDF.
4. Nếu text PDF quá ngắn và OCR được bật, crawler dùng OCR để tạo lại HTML paragraph.
5. Nếu PDF text vẫn kém, văn bản được đưa vào `pdf_review.parquet` thay vì đưa thẳng vào context RAG.

### Tiêu chí parse cấu trúc

Parser nhận diện các đơn vị pháp luật phổ biến:

- `Điều ...` cho article.
- `1.`, `2.`, ... cho clause.
- `a)`, `b)`, ... cho point.
- `PHỤ LỤC`, `Phụ lục` cho annex.
- `Mẫu số`, `MẪU SỐ` cho form.
- `<table>` cho bảng.
- Roman section như `I.`, `II.` khi văn bản dùng bố cục dạng mục lớn thay vì điều.

Mỗi đơn vị được gán `stable_anchor` để RAG có thể trích dẫn ổn định ở cấp điều/khoản/điểm/bảng/phụ lục thay vì chỉ trích dẫn toàn văn bản.

### Tiêu chí export

Lệnh `export-parquet` xuất các bảng:

- `metadata.parquet`: metadata văn bản và version hiện hành.
- `context.parquet`: context RAG gồm `DOCUMENT`, `ARTICLE`, `CLAUSE`, `POINT`, `TABLE`, `FORM`, `ANNEX`.
- `relationships.parquet`: quan hệ giữa văn bản.
- `anchors.parquet`: anchor ổn định cho trích dẫn.
- `pdf_review.parquet`: văn bản PDF cần review thủ công.

Mặc định chỉ export current version. Có thể dùng `--all-versions` nếu cần xuất toàn bộ version đã lưu.

## Workaround Đã Implement

- **VBPL API không ổn định**: khi API trả HTTP 400 hoặc payload không `success`, fetcher tự thử fallback Thư Viện Pháp Luật.
- **Fallback URL khó khớp**: hỗ trợ file mapping `document_id,url`; nếu chưa có mapping thì search Google/site search Thư Viện Pháp Luật và chấm điểm theo token slug + số/ký hiệu văn bản.
- **Trang Thư Viện Pháp Luật có nhiều layout**: extractor thử nhiều selector như `#divContentDoc`, `#divNoiDung`, `#divFullText`, `.contentdoc`, `.vanban-content`, rồi fallback sang container dài nhất nếu đủ nội dung.
- **Trang fallback cần cookie**: fetcher đọc cookie từ file Netscape hoặc chuỗi `name=value` qua `LAW_CRAWLER_THUVIENPHAPLUAT_COOKIE_FILE`.
- **PDF-only document**: tách `PDF_TEXT` ra `pdf_review.parquet` khi text nhúng có rủi ro thấp chất lượng; OCR chỉ đưa vào pipeline chính khi bật rõ bằng biến môi trường.
- **OCR dependency nhạy Python version**: OCR extra tách riêng vì `vietocr==0.3.13` không phù hợp Python 3.13.
- **Parser quality regression**: có lệnh `requeue-quality-issues` để requeue văn bản đã crawl nhưng rỗng, không parse được article, hoặc title article dài bất thường.
- **Retry crawl sau khi fix fetcher/parser**: `crawl-site --retry-previous` retry cả job `SKIPPED` và `FAILED` đã hết attempts.
- **MySQL disconnect khi crawl dài**: thao tác DB có retry và dispose connection pool trước khi thử lại.
- **Số điều/khoản/điểm bị lặp**: anchor có `occurrence_index`, tránh mất dữ liệu khi văn bản có cùng số điều/khoản trong phụ lục hoặc phần đặc biệt.
- **Export lớn**: exporter ghi Parquet theo batch, có file tạm và hỗ trợ `--tables` để resume từng bảng.
- **Audit duplicate identity**: schema có bảng review cho trường hợp nhiều `document_id` có cùng identity pháp lý nhưng khác source/version.

## Chạy Local

```bash
cd dataset/vietnamese_legal_documents/creation/crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d law-crawler-mysql
vn-law-crawler init-db
```

Chạy crawl thử một URL:

```bash
vn-law-crawler crawl-url --api "https://vbpl.vn/van-ban/chi-tiet/example--12345"
```

Discover từ sitemap và crawl thử giới hạn nhỏ:

```bash
vn-law-crawler crawl-site --discover-limit 100 --crawl-limit 20 --delay-seconds 0.5
```

Resume queue đã có, không đọc lại sitemap:

```bash
vn-law-crawler crawl-site --skip-discovery --retry-previous --delay-seconds 0.5
```

Export sang path tương thích với service hiện tại ở root repo:

```bash
vn-law-crawler export-parquet --output-dir ../../../../data_usable/current_new
```

Validate export:

```bash
python scripts/validate_export.py --output-dir ../../../../data_usable/current_new
```

Preview export bằng UI local:

```bash
python scripts/preview_dataset.py --data-dir ../../../../data_usable/current_new --open
```

## OCR Cho PDF Scan

OCR không bật mặc định. Nếu cần xử lý PDF scan:

```bash
pip install -e ".[ocr]"
export LAW_CRAWLER_ENABLE_PDF_OCR=true
export LAW_CRAWLER_PDF_OCR_BACKEND=paddle_vietocr
export LAW_CRAWLER_PDF_OCR_DEVICE=cpu
```

Khi PDF embedded text ngắn hơn `LAW_CRAWLER_PDF_TEXT_MIN_CHARS`, crawler có thể dùng PaddleOCR để detect vùng chữ và VietOCR để nhận dạng tiếng Việt. Nội dung OCR được đánh dấu `PDF_OCR`; nội dung PDF text chất lượng thấp vẫn đi vào review.

## Test

```bash
cd dataset/vietnamese_legal_documents/creation/crawler
source .venv/bin/activate
pytest
```

## Lưu Ý Khi Upload GitHub

- Không commit `.env`, cookie file, DB dump, Parquet export lớn hoặc report review tạm.
- `.env.example` chỉ dùng placeholder local.
- Nếu cần commit Parquet artifact lớn, dùng Git LFS.
- Crawler này là công cụ tạo dataset; service runtime hiện vẫn đọc dữ liệu ở root `data_usable/`.
