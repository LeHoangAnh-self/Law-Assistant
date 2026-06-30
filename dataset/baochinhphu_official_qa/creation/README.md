# BaoChinhPhu Q&A Dataset Creation

This folder contains the scripts used to create the BaoChinhPhu official Q&A evaluation dataset.

## Scripts

- `build_evaluation_dataset.py`: preferred entrypoint for building `data_usable/rag_test_set.json`.
- `baochinhphu_dataset.py`: scraper and parser implementation. It can also be run directly.

Both scripts should be run from the repository root.

## Build The Usable Dataset

```bash
python dataset/baochinhphu_official_qa/creation/build_evaluation_dataset.py \
  --limit 20 \
  --max-pages 3 \
  --law-db-path data_usable/rag/law_documents.parquet
```

Default output:

```text
dataset/baochinhphu_official_qa/data_usable/rag_test_set.json
```

Use `--output` to write a separate sample or experiment file:

```bash
python dataset/baochinhphu_official_qa/creation/build_evaluation_dataset.py \
  --limit 50 \
  --max-pages 5 \
  --output dataset/baochinhphu_official_qa/data_usable/rag_test_set.sample.json
```

## Options

- `--limit`: target total number of items in the final output dataset.
- `--max-pages`: number of listing/timeline pages to scan.
- `--output`: JSON output path.
- `--delay-seconds`: download delay between requests. Default is `0.5`.
- `--law-db-path`: local prepared legal-document Parquet used to validate direct links.
- `--oldest-first`: scan listing pages from older to newer. By default, the builder scans from newer to older.
- `--related-depth`: use related-article links as additional candidate pages. Default is `1`.
- `--require-all-linked-documents`: stricter mode; keep an article only if every direct legal-document link matches the local DB.

The Scrapy crawler uses one concurrent request and obeys `robots.txt`.

## Search Order

By default, the crawler scans BaoChinhPhu listing pages from newer to older:

```text
https://baochinhphu.vn/tra-loi-cong-dan.htm
https://baochinhphu.vn/timelinelist/102301/2.htm
https://baochinhphu.vn/timelinelist/102301/3.htm
...
```

This means a small `--limit` will prefer newer Q&A records first. Use `--oldest-first` only when building a historical sample.

## Incremental Updates

The builder is incremental. Before crawling, it reads the existing output JSON and skips articles whose `source_url` is already present. New valid records are written to a temporary file, merged with existing records, deduplicated by `source_url`, trimmed to `--limit`, and then saved back to the requested output path.

This lets you extend the dataset without rebuilding from scratch:

```bash
python dataset/baochinhphu_official_qa/creation/build_evaluation_dataset.py \
  --limit 100 \
  --max-pages 10
```

`--limit` is the target final dataset size. For example, if the output file already contains 80 records and you run with `--limit 100`, the crawler will accept at most 20 new records. If the output already has at least 100 records, the run exits without crawling.

## Inclusion And Extraction Rules

The builder keeps an article only when both conditions are true:

- The article body contains at least one direct legal-document link.
- At least one direct linked legal document matches the local Law Assistant database.

Direct legal-document links are currently recognized as:

```text
https://vanban.chinhphu.vn/?pageid=27160&docid=...
```

The matcher uses:

- `so_ky_hieu` for anchor text such as `170/2025/NĐ-CP`.
- normalized title matching for anchor text such as `Luật Cán bộ, công chức`.

For the usable dataset, the builder extracts only matched legal-document links. Direct links that do not match the local DB are ignored and are not written to the output record. The same rule is applied to `expected_legal_citations`: citations are kept only when their document number or normalized document title matches one of the linked local documents.

For each kept citation, `provision` and `citation_text` are extracted from the official answer text. Legal document fields are overwritten from the matched database row:

- `document_id`
- `document_name`
- `document_type`
- `document_number`
- `document_date`
- `document_status`

Use `--require-all-linked-documents` when you want to reject articles that contain any direct legal-document link missing from the local DB.

## Related Articles

Related articles are not saved in usable dataset records. They are used only as discovery candidates. When a crawled article contains related Q&A links, the crawler schedules those pages up to `--related-depth`.

This helps find older topic-specific Q&A pages without storing recommendation metadata as ground truth.

## Parser Output

The parser extracts:

- article title, summary, category, tags, dates, image URL, and source URL
- `question` built from the official summary and title
- `expected_answer` beginning at official-answer marker phrases where possible
- `recommendation_text` for similarity/recommendation experiments
- `expected_legal_citations` and `expected_citation_text` from the official answer
- `direct_legal_document_links` and `matched_direct_legal_documents`, limited to local DB matches

The citation extractor is designed to keep adjacent citations separate, for example:

```text
Khoản 1 Điều 72 Quyết định số 505/QĐ-BHXH ngày 27/3/2020
Điều 46 Quyết định số 595/QĐ-BHXH
```

## Validation

Run the focused test after parser changes:

```bash
cd rag-service
pytest tests/test_baochinhphu_dataset.py
```

Run lint for the dataset creation scripts:

```bash
cd rag-service
ruff check \
  ../dataset/baochinhphu_official_qa/creation/baochinhphu_dataset.py \
  ../dataset/baochinhphu_official_qa/creation/build_evaluation_dataset.py \
  tests/test_baochinhphu_dataset.py
```

Before using a newly generated file for model evaluation, manually inspect a small sample for:

- missing or empty `expected_answer`
- merged or truncated legal citations
- expected citations that reference documents outside `matched_direct_legal_documents`
- stale or incorrect `published_date` and `retrieval_cutoff_date`
- source URLs outside the BaoChinhPhu official Q&A section

## Raw Data

The current builder writes the usable JSON directly. If raw HTML or source manifests are needed for auditability, save them under:

```text
dataset/baochinhphu_official_qa/data_raw/
```

Do not overwrite raw captures during cleaning or schema migration.
