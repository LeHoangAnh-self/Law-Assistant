# RAG Service

FastAPI Retrieval-Augmented Generation service for Law Assistant.

`law-service` is the source of truth for legal document data. `rag-service` indexes chunks into Qdrant and answers questions with cited passages.

## Stack

- FastAPI
- Qdrant
- Redis + Celery
- RabbitMQ bridge
- SentenceTransformers embeddings
- CrossEncoder reranking

## Requirements

- Python 3.11 to 3.13
- Docker + Docker Compose
- Running `law-service` at `http://localhost:8080`

## Setup

```bash
cd /home/lee/Documents/LawAssistant/rag-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Start Qdrant/Redis:

```bash
docker compose up -d
```

Run API:

```bash
uvicorn rag_service.main:app --app-dir app --reload --port 8090
```

Health check:

```bash
curl http://localhost:8090/health
```

Document UI:

```text
http://localhost:8090/documents
```

## Run Worker and Bridge

Worker:

```bash
python -m celery -A rag_service.worker:celery_app worker --loglevel=info --concurrency=1
```

RabbitMQ bridge:

```bash
python -m rag_service.rabbit_bridge
```

## Indexing Flow

1. Import documents into `law-service` first.
2. Ask `law-service` to publish embedding events:

```bash
curl -X POST "http://localhost:8080/api/documents/embedding-events"
```

3. Monitor queue/worker logs.
4. Audit indexed coverage:

```bash
python -m rag_service.index_audit
```

If embedding dimension or chunking rules change, recreate the collection before reindexing:

```bash
curl -X DELETE "http://localhost:6333/collections/legal_document_chunks"
```

## Ask Questions

```bash
curl -X POST "http://localhost:8090/api/rag/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Văn bản nào quy định về hiệu lực thi hành?","top_k":5}'
```

## Evaluation

Run evaluation on bundled test set:

```bash
python -m rag_service.evaluation \
  --questions-file evaluation/rag_test_set.json \
  --limit 20 \
  --top-k 5 \
  --reset
```

Generated `rag_eval_results.csv/jsonl` files are local artifacts and are ignored by git.

## Tests

```bash
pytest
ruff check app tests
```
