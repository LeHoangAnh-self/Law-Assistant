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

The listing API currently reports more rows than it returns in one response. For production coverage beyond the listing cap, use direct detail-ID scanning:

```bash
vn-law-qna-crawler crawl-government-qna \
  --discovery-mode id-range \
  --cookie-file /home/lee/Downloads/bachkhoaluat_vn_cookies.json \
  --id-start 22403 \
  --id-end 1 \
  --delay-seconds 0.25 \
  --progress-every 100
```

If `--id-start` is omitted, the crawler discovers the latest Q&A ID from the listing endpoint. Use `--limit` with `id-range` to stop after a target number of persisted Q&A items:

```bash
vn-law-qna-crawler crawl-government-qna \
  --discovery-mode id-range \
  --cookie-file /home/lee/Downloads/bachkhoaluat_vn_cookies.json \
  --limit 500 \
  --delay-seconds 0.25 \
  --progress-every 100
```

Use `--max-consecutive-misses` only for exploratory scans where you do not know the valid ID range; for a full historical crawl, prefer explicit `--id-end 1`.

Export dataset files:

```bash
vn-law-qna-crawler export-government-qna \
  --output-dir /home/lee/Documents/LawAssistant/data_usable/government_qna
```

Exported files:

- `government_qna.parquet`: raw Q&A rows with source URLs and citation coverage.
- `government_qna_citations.parquet`: extracted citations and match status, including article/clause/point refs when present.
- `government_qna_training.parquet`: `prompt`/`completion` pairs.
- `government_qna_benchmark.parquet`: only matched citations with `expected_document_id`, `article_refs`, `clause_refs`, and `point_refs`.

Audit whether the matched Q&A citations are deployment-ready in the retrieval index:

```bash
vn-law-qna-crawler audit-retrieval-readiness \
  --qdrant-url http://localhost:6333 \
  --qdrant-collection legal_document_chunks \
  --output-jsonl /home/lee/Documents/LawAssistant/data_usable/government_qna/retrieval_readiness_audit.jsonl \
  --progress-every 500
```

Key statuses in the JSONL output:

- `RETRIEVAL_READY`: cited document and cited article/clause/point are present in Qdrant payloads.
- `DOCUMENT_NOT_INDEXED`: document exists in `law-service` DB but has no chunks in Qdrant.
- `ARTICLE_NOT_INDEXED`, `CLAUSE_NOT_INDEXED`, `POINT_NOT_INDEXED`: document is indexed but the expected structural reference is missing from indexed chunks.
- `NO_STRUCTURAL_REFS`: citation matched a document but the Q&A answer did not cite a specific article/clause/point.

## Notes

- `government_qna_benchmark.parquet` is empty when cited documents are not present in `legal_documents`.
- Citation gaps are preserved as `MISSING`, `AMBIGUOUS`, or `UNRESOLVED`; they are useful for deciding which legal documents to crawl/import next.
- Run `audit-retrieval-readiness` before deployment. Missing Qdrant documents mean reindexing is required; article/clause/point gaps usually mean the source content or chunk metadata needs repair before the item can be used as a strict retrieval benchmark.
- The crawler accepts both `QNA_CRAWLER_DATABASE_URL` and, as a fallback for compatibility, `LAW_CRAWLER_DATABASE_URL` for the Q&A dataset DB. The document DB must be set separately with `QNA_CRAWLER_DOCUMENT_DATABASE_URL` or `--document-database-url`.

## Test

```bash
cd /home/lee/Documents/LawAssistant/QnA_crawler
source .venv/bin/activate
pytest -q
```
```bash
cd /home/lee/Documents/LawAssistant/QnA_crawler
docker compose up -d qna-crawler-mysql

export QNA_CRAWLER_DATABASE_URL="mysql+mysqlconnector://qna:qna@127.0.0.1:3308/qna_dataset"
export QNA_CRAWLER_DOCUMENT_DATABASE_URL="mysql+mysqlconnector://law:law@127.0.0.1:3306/law_service"

vn-law-qna-crawler crawl-government-qna \
  --discovery-mode id-range \
  --cookie-file /home/lee/Downloads/bachkhoaluat_vn_cookies.json \
  --id-end 1 \
  --delay-seconds 0.25 \
  --progress-every 100
  ```
