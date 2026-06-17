# Law Assistant

Law Assistant is a local Vietnamese legal-document platform with two services:

- `law-service`: Spring Boot API for legal-document metadata, content, relationships, and import.
- `rag-service`: FastAPI retrieval service for chunk indexing, vector search, reranking, and answer generation.

The prepared dataset lives in `data_usable/`.

## Repository Layout

```text
.
├── data_usable/        # Final cleaned dataset
├── law-service/        # Spring Boot API, MySQL importer, Redis cache, RabbitMQ events
├── rag-service/        # FastAPI RAG service, Qdrant integration, Celery workers
└── scripts/            # Dataset preparation utilities
```

## Data

Use `data_usable/current` to import data into MySQL:

```text
data_usable/current/metadata.parquet
data_usable/current/content.parquet
data_usable/current/relationships.parquet
```

Use `data_usable/rag` for retrieval and embedding workflows:

```text
data_usable/rag/law_documents.parquet
data_usable/rag/law_chunks.parquet
data_usable/rag/law_relationships.parquet
```

Dataset summary:

- Documents: `127,267`
- Cleaned relationships: `651,966`
- RAG chunks: `1,203,686`
- Chunking: `1,500` characters with `200` character overlap

See [data_usable/README.md](data_usable/README.md) for details.

## GitHub Data Note

The Parquet files are large. This repository is configured to track `*.parquet` with Git LFS via `.gitattributes`.

Before pushing the dataset to GitHub, install and enable Git LFS:

```bash
git lfs install
git lfs track "*.parquet"
```

Then commit `.gitattributes` together with the data files.

## Quick Start

### 1. Start the Law Service dependencies

```bash
cd law-service
docker compose down -v
docker compose up -d
```

Wait for MySQL:

```bash
until docker compose exec mysql mysqladmin ping -h localhost -ulaw -plaw --silent; do
  echo "waiting for mysql..."
  sleep 2
done
```

### 2. Run the Law Service

```bash
mvn spring-boot:run
```

Health check:

```bash
curl "http://localhost:8080/actuator/health"
```

### 3. Import the cleaned dataset

Run this from `law-service` while the service is running:

```bash
curl -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current"
```

Expected import counts:

```json
{
  "metadataRows": 127267,
  "contentRows": 127267,
  "relationshipRows": 651966
}
```

Verify one document:

```bash
curl "http://localhost:8080/api/documents/4260"
```

### 4. Start the RAG Service

```bash
cd ../rag-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d
uvicorn rag_service.main:app --app-dir app --reload --port 8090
```

Ask a retrieval question:

```bash
curl -X POST "http://localhost:8090/api/rag/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Văn bản nào quy định về hiệu lực thi hành?","top_k":5}'
```

## Useful Commands

Run Java tests:

```bash
cd law-service
mvn test
```

Run Python tests:

```bash
cd rag-service
source .venv/bin/activate
pytest
```

Recreate the prepared dataset from source Parquet files, if source files are restored:

```bash
python3 scripts/prepare_law_assistant_dataset.py --input-dir data --output-dir data_usable
```
