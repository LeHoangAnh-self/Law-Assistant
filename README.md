# Law Assistant

Law Assistant is a local-first Vietnamese legal assistant platform. It combines a structured legal-document API with a retrieval-augmented generation (RAG) service so users can search legal documents, retrieve relevant passages, and generate source-backed answers in Vietnamese.

The repository is currently a working technical prototype, not a hosted product. It is designed to demonstrate the core product advantages needed for a legal AI assistant: traceable sources, domain-specific retrieval, document metadata filtering, and a service boundary that keeps legal data management separate from AI answer generation.

> This project is for legal research and product development. It does not provide legal advice.

## Why This Project Exists

Vietnamese legal research is difficult because useful answers often depend on exact document status, effective dates, issuing authority, document relationships, and article-level context. A generic chatbot can produce fluent text, but it does not automatically know which source was retrieved, whether the document is still valid, or which legal passage supports the conclusion.

Law Assistant is built around those constraints:

- **Grounded answers**: every RAG answer includes retrieved source references.
- **Legal metadata awareness**: documents can be filtered by type, validity status, scope, authority, external ID, and date ranges.
- **Vietnamese-first retrieval**: the embedding model and default answer language are configured for Vietnamese legal text.
- **Separation of concerns**: `law-service` owns canonical legal data; `rag-service` owns indexing, retrieval, reranking, and answer generation.
- **Local development path**: MySQL, Redis, RabbitMQ, and Qdrant run locally with Docker Compose.

## What Is Implemented Today

### Legal Document Service

`law-service` is a Spring Boot API for importing, storing, searching, and serving legal documents.

Implemented capabilities:

- Import prepared Parquet data into MySQL.
- Store document metadata, full content, and document relationships.
- Search documents with pagination and filters.
- Return full document detail by ID.
- Cache document detail with Redis.
- Publish RabbitMQ embedding-update events for one document or the full corpus.
- Manage schema changes with Flyway migrations.
- Expose health checks through Spring Boot Actuator.

Key endpoints:

```text
GET  /actuator/health
POST /api/imports/provided-data
GET  /api/documents
GET  /api/documents/ids
GET  /api/documents/{id}
POST /api/documents/{id}/embedding-events
POST /api/documents/embedding-events
```

### RAG Service

`rag-service` is a FastAPI service that retrieves legal passages and generates cited answers.

Implemented capabilities:

- Consume document update events through a RabbitMQ bridge.
- Queue indexing work with Celery and Redis.
- Chunk legal documents for retrieval.
- Embed text with a Vietnamese legal embedding model.
- Store vectors in Qdrant.
- Rerank retrieved candidates with a CrossEncoder.
- Classify common Vietnamese legal question types to improve retrieval.
- Generate answers through a configurable LLM provider, with a stub provider for local development.
- Return answer text, rewritten query, classification, retrieval query, and source references.
- Provide an indexing audit command and evaluation runner.
- Expose a lightweight document picker UI at `/documents`.
- Add optional Langfuse/OpenTelemetry observability hooks.

Key endpoints:

```text
GET  /health
GET  /documents
GET  /api/documents
GET  /api/documents/{document_id}
POST /api/rag/ask
```

### Test UI

`UI_test` is a small browser interface for manual testing.

Implemented capabilities:

- Ask questions against the RAG API.
- Inspect document detail pages.
- Test API health and OpenAI-compatible configuration.
- Keep local conversation state for manual QA.

## Architecture

```text
Prepared legal data
       |
       v
+------------------+       MySQL / Redis / RabbitMQ
|   law-service    |--------------------------------+
| Spring Boot API  |                                |
+------------------+                                |
       |                                           events
       | document API                                |
       v                                             v
+------------------+       Redis / Celery       +----------+
|   rag-service    |--------------------------->|  Qdrant  |
|   FastAPI RAG    |       indexing jobs        | vectors  |
+------------------+                            +----------+
       |
       v
 Answer + cited source references
```

## Repository Layout

```text
LawAssistant/
├── law-service/      # Spring Boot legal document API and importer
├── rag-service/      # FastAPI retrieval, indexing, reranking, and answer API
├── UI_test/          # Optional browser UI for manual testing
├── data_usable/      # Prepared local data tables
├── dataset/          # Dataset workspace and creation notes
└── scripts/          # Data preparation helpers
```

## Data Included

The local runnable data lives in `data_usable/`.

Current prepared data includes:

- `data_usable/current_new/metadata.parquet`
- `data_usable/current_new/context.parquet`
- `data_usable/current_new/relationships.parquet`
- `data_usable/current_new/anchors.parquet`
- `data_usable/rag/law_documents.parquet`
- `data_usable/rag/law_chunks.parquet`
- `data_usable/rag/law_relationships.parquet`
- `data_usable/audit/data_quality_report.json`
- `data_usable/audit/bad_documents.csv`

The `law-service` importer accepts either `content.parquet` or `context.parquet` as document content input. The current root dataset uses `context.parquet`.

Expected import totals for the prepared data:

- `metadataRows`: `127267`
- `contentRows`: `127267`
- `relationshipRows`: `651966`

If large Parquet artifacts are committed to GitHub, use Git LFS.

## Technology Stack

| Layer | Current implementation |
| --- | --- |
| Legal document API | Java 19, Spring Boot 3.5, Spring Data JPA |
| Relational storage | MySQL |
| Schema migration | Flyway |
| Cache | Redis |
| Eventing | RabbitMQ |
| RAG API | Python 3.11+, FastAPI, Pydantic |
| Async indexing | Celery, Redis, RabbitMQ bridge |
| Vector store | Qdrant |
| Embeddings | `mainguyen9/vietlegal-harrier-0.6b` |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| LLM integration | Configurable OpenAI-compatible/chat-completions style client, local stub by default |
| Observability | Langfuse and OpenTelemetry hooks |

## Quick Start

### Prerequisites

- Java 19+
- Maven
- Python 3.11+
- Docker and Docker Compose

### 1. Start Law Service Dependencies

```bash
cd /home/lee/Documents/LawAssistant/law-service
docker compose up -d
```

Wait for MySQL:

```bash
until docker compose exec mysql mysqladmin ping -h localhost -ulaw -plaw --silent; do
  echo "waiting for mysql..."
  sleep 2
done
```

### 2. Run Law Service

```bash
mvn spring-boot:run
```

Health check:

```bash
curl http://localhost:8080/actuator/health
```

### 3. Import Legal Documents

Run while `law-service` is running:

```bash
curl -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current_new"
```

Verify an imported document:

```bash
curl "http://localhost:8080/api/documents/4260"
```

### 4. Start RAG Service Dependencies

```bash
cd /home/lee/Documents/LawAssistant/rag-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d
```

### 5. Run RAG API

```bash
uvicorn rag_service.main:app --app-dir app --reload --port 8090
```

Health check:

```bash
curl http://localhost:8090/health
```

Ask a question:

```bash
curl -X POST "http://localhost:8090/api/rag/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Văn bản nào quy định về hiệu lực thi hành?","top_k":5}'
```

### 6. Index Documents for Retrieval

In separate terminals, run the worker and RabbitMQ bridge:

```bash
cd /home/lee/Documents/LawAssistant/rag-service
source .venv/bin/activate
python -m celery -A rag_service.worker:celery_app worker --loglevel=info --concurrency=1
```

```bash
cd /home/lee/Documents/LawAssistant/rag-service
source .venv/bin/activate
python -m rag_service.rabbit_bridge
```

Then publish embedding events from `law-service`:

```bash
curl -X POST "http://localhost:8080/api/documents/embedding-events"
```

Audit indexed coverage:

```bash
cd /home/lee/Documents/LawAssistant/rag-service
source .venv/bin/activate
python -m rag_service.index_audit
```

## Optional Browser UI

```bash
cd /home/lee/Documents/LawAssistant/UI_test
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8091
```

Open:

```text
http://localhost:8091
```

The RAG service also exposes its document picker at:

```text
http://localhost:8090/documents
```

## Evaluation and Quality Checks

Run law-service tests:

```bash
cd /home/lee/Documents/LawAssistant/law-service
mvn test
```

Run rag-service tests and linting:

```bash
cd /home/lee/Documents/LawAssistant/rag-service
source .venv/bin/activate
pytest
ruff check app tests
```

Run RAG evaluation on the bundled test set:

```bash
cd /home/lee/Documents/LawAssistant/rag-service
source .venv/bin/activate
python -m rag_service.evaluation \
  --questions-file evaluation/rag_test_set.json \
  --limit 20 \
  --top-k 5 \
  --reset
```

## Current Limitations

- The project is optimized for local development, not production deployment.
- The default LLM provider is a local stub. Real answer generation requires configuring an LLM provider in `rag-service/.env`.
- Legal data freshness depends on the prepared dataset artifacts in this repository.
- The UI in `UI_test` is for manual testing and demos, not a polished production frontend.
- Generated answers must be reviewed by a qualified human before legal use.

## Roadmap Ideas

- Production frontend with document search, cited chat, and source inspection.
- Dataset refresh pipeline and provenance reporting.
- Stronger citation validation and answer refusal behavior when sources are weak.
- User-facing evaluation dashboard for retrieval quality.
- Deployment profiles for staging and production infrastructure.
- Authentication, audit logs, and workspace management for organizational use.

## More Documentation

- [law-service README](law-service/README.md)
- [rag-service README](rag-service/README.md)
- [UI_test README](UI_test/README.md)
- [data_usable README](data_usable/README.md)
- [dataset README](dataset/README.md)
