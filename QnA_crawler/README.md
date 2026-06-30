# Government Q&A Crawler

Standalone crawler for government Q&A items used to build Law Assistant retrieval benchmarks and fine-tuning datasets.

Source:

- Listing: `https://bachkhoaluat.vn/hoi-dap-nha-nuoc`
- Metadata API: `https://api.bachkhoaluat.vn/api/businessEssential?cmcndn=74`
- Full answer: original government URL from `linkTrichDan`
- Fallback answer: DOCX file from `linkDownLoadWord`

The crawler stores Q&A rows in `government_qna_items`, extracted legal citations in `government_qna_citations`, and checks cited documents against `legal_documents` before labeling benchmark rows.

Storage is intentionally split:

- `QNA_CRAWLER_DATABASE_URL`: write target for the eval/fine-tune Q&A dataset only.
- `QNA_CRAWLER_DOCUMENT_DATABASE_URL`: read-only source database containing `legal_documents` for citation matching.

`vn-law-qna-crawler init-db` only initializes Q&A tables. It does not create or modify the document database.

## Setup

```bash
cd /home/lee/Documents/LawAssistant/QnA_crawler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Start the dedicated Q&A dataset database:

```bash
cp .env.example .env
docker compose up -d qna-crawler-mysql
```

Point the Q&A crawler at its own dataset database:

```bash
export QNA_CRAWLER_DATABASE_URL="mysql+mysqlconnector://qna:qna@127.0.0.1:3308/qna_dataset"
```

Point citation matching at the existing document database:

```bash
export QNA_CRAWLER_DOCUMENT_DATABASE_URL="mysql+mysqlconnector://law:law@127.0.0.1:3306/law_service"
```

For local smoke databases:

```bash
export QNA_CRAWLER_DATABASE_URL="sqlite:////tmp/law_qna.sqlite"
export QNA_CRAWLER_DOCUMENT_DATABASE_URL="sqlite:////tmp/law_documents.sqlite"
```

## Run

Initialize tables:

```bash
vn-law-qna-crawler init-db
```

Crawl a small sample:

```bash
vn-law-qna-crawler crawl-government-qna \
  --cookie-file /home/lee/Downloads/bachkhoaluat_vn_cookies.json \
  --limit 100 \
  --delay-seconds 0.25
```

Crawl all available Q&A:

```bash
vn-law-qna-crawler crawl-government-qna \
  --cookie-file /home/lee/Downloads/bachkhoaluat_vn_cookies.json \
  --delay-seconds 0.25
```

Export dataset files:

```bash
vn-law-qna-crawler export-government-qna \
  --output-dir /home/lee/Documents/LawAssistant/data_usable/government_qna
```

Exported files:

- `government_qna.parquet`: raw Q&A rows with source URLs and citation coverage.
- `government_qna_citations.parquet`: extracted citations and match status.
- `government_qna_training.parquet`: `prompt`/`completion` pairs.
- `government_qna_benchmark.parquet`: only matched citations with `expected_document_id`.

## Notes

- `government_qna_benchmark.parquet` is empty when cited documents are not present in `legal_documents`.
- Citation gaps are preserved as `MISSING`, `AMBIGUOUS`, or `UNRESOLVED`; they are useful for deciding which legal documents to crawl/import next.
- The crawler accepts both `QNA_CRAWLER_DATABASE_URL` and, as a fallback for compatibility, `LAW_CRAWLER_DATABASE_URL` for the Q&A dataset DB. The document DB must be set separately with `QNA_CRAWLER_DOCUMENT_DATABASE_URL` or `--document-database-url`.

## Test

```bash
cd /home/lee/Documents/LawAssistant/QnA_crawler
source .venv/bin/activate
pytest -q
```
