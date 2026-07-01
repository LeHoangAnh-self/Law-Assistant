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
curl -H "X-Admin-Token: $LAW_ADMIN_TOKEN" \
  -X POST "http://localhost:8080/api/documents/embedding-events"
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

## Evaluate Reranking

The default reranker baseline is `Qwen/Qwen3-Reranker-0.6B`. Evaluate it against the
government Q&A citation benchmark after Qdrant has been indexed:

```bash
python -m rag_service.evaluation \
  --dataset-dir /home/lee/Documents/LawAssistant/data_usable/government_qna \
  --candidate-k 40 \
  --rerank-k 10 \
  --output-json /home/lee/Documents/LawAssistant/data_usable/government_qna/qwen3_reranker_eval.json \
  --training-jsonl /home/lee/Documents/LawAssistant/data_usable/government_qna/qwen3_reranker_training.jsonl
```

Reported metrics separate first-stage retrieval from reranking:

- `document_recall_at_candidate_k`: expected document present before reranking.
- `citation_recall_at_candidate_k`: expected document plus cited article/clause/point present before reranking.
- `document_mrr_at_k` and `document_ndcg_at_k`: reranked document-level quality.
- `citation_mrr_at_k`, `citation_ndcg_at_k`, and `exact_citation_hit_at_k`: strict legal citation quality.

The optional `--training-jsonl` output uses `query`, `pos`, `neg`, and `prompt` fields so it can
seed future reranker fine-tuning when the Q&A dataset is refreshed.

## Tests

```bash
pytest
ruff check app tests
```
