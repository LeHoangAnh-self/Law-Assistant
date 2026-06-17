# RAG Service

FastAPI retrieval augmented generation service for Law Assistant.

The Law Service remains the source of truth for imported legal documents. The RAG Service indexes document chunks into Qdrant, retrieves and reranks candidate passages, builds Vietnamese legal prompts with citations, and delegates answer generation to a configured LLM provider.

## Stack

- FastAPI for the HTTP API
- Qdrant for vector search
- Redis and Celery for async indexing
- RabbitMQ bridge for Law Service embedding events
- SentenceTransformers for embeddings
- CrossEncoder reranking
- Langfuse and OpenTelemetry hooks

Vietnamese-first defaults:

- Embedding model: `mainguyen9/vietlegal-harrier-0.6b`
- Embedding dimension: `1024`
- Query instruction: `Instruct: Given a Vietnamese legal question, retrieve relevant legal passages that answer the question\nQuery:`
- Chat model name: `luanngo/Qwen3-4B-VietNamese-Legal-Chat`
- Answer language: Vietnamese

## Requirements

- Python 3.11 to 3.13
- Docker and Docker Compose
- Running `law-service` on `http://localhost:8080`

## Local Setup

Start the Law Service first:

```bash
cd ../law-service
docker compose up -d
mvn spring-boot:run
```

Create the Python environment:

```bash
cd ../rag-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Start Qdrant:

```bash
docker compose up -d
```

Run the API:

```bash
uvicorn rag_service.main:app --app-dir app --reload --port 8090
```

Document picker UI:

```text
http://localhost:8090/documents
```

## Embedding Model

Download the default embedding model once:

```bash
export EMBEDDING_MODEL_NAME=mainguyen9/vietlegal-harrier-0.6b
export EMBEDDING_DIMENSION=1024
export EMBEDDING_DEVICE=cpu
export EMBEDDING_LOCAL_FILES_ONLY=false
python -m rag_service.download_embedding_model
```

After the download succeeds:

```bash
export EMBEDDING_LOCAL_FILES_ONLY=true
```

For CUDA indexing, keep worker concurrency low:

```bash
export EMBEDDING_DEVICE=cuda
export EMBEDDING_BATCH_SIZE=16
export EMBEDDING_LOCAL_FILES_ONLY=true
```

## Workers

Run the Celery worker:

```bash
python -m celery -A rag_service.worker:celery_app worker --loglevel=info --concurrency=1
```

Run the RabbitMQ bridge:

```bash
python -m rag_service.rabbit_bridge
```

Keep `--concurrency=1` for local indexing. Each worker process loads its own embedding model.

If the queue needs to be cleared:

```bash
python -m celery -A rag_service.worker:celery_app purge -f
```

## Indexing

Ask the Law Service to publish embedding events:

```bash
curl -X POST "http://localhost:8080/api/documents/embedding-events"
```

Audit Qdrant coverage:

```bash
python -m rag_service.index_audit
```

If chunking rules or embedding dimensions change, recreate the Qdrant collection before reindexing:

```bash
curl -X DELETE "http://localhost:6333/collections/legal_document_chunks"
```

## Ask a Question

With the API running:

```bash
curl -X POST "http://localhost:8090/api/rag/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Văn bản nào quy định về hiệu lực thi hành?","top_k":5}'
```

With `LLM_PROVIDER=stub`, responses include retrieved citations and a prompt-shaped draft. To use an OpenAI-compatible local server:

```bash
export LLM_PROVIDER=openai-compatible
export LLM_API_BASE_URL=http://localhost:8000/v1
export LLM_API_KEY=local-dev-key
export LLM_MODEL=luanngo/Qwen3-4B-VietNamese-Legal-Chat
```

## Evaluation

Run the included evaluation set:

```bash
python -m rag_service.evaluation \
  --questions-file evaluation/rag_test_set.json \
  --limit 20 \
  --top-k 5 \
  --reset
```

Build a small fresh evaluation set from the Government Portal citizen/business answer section:

```bash
python -m rag_service.evaluation_dataset \
  --limit 20 \
  --max-pages 3 \
  --output evaluation/rag_test_set.json
```

Estimate Celery queue time:

```bash
scripts/redis_queue_eta.sh
```

## Tests

```bash
pytest
ruff check .
```
