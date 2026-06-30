# Law Assistant

Law Assistant is a local Vietnamese legal assistant stack with:

- `law-service`: Spring Boot API for legal documents and import.
- `rag-service`: FastAPI RAG service for retrieval, reranking, and answer generation.
- `UI_test`: optional browser chat UI for manual testing.

## Repository Layout

```text
LawAssistant/
├── law-service/
├── rag-service/
├── UI_test/
├── data_usable/
├── dataset/
└── scripts/
```

## Prerequisites

- Java 19+
- Maven
- Python 3.11+
- Docker + Docker Compose

## 1) Start Law Service

```bash
cd /home/lee/Documents/LawAssistant/law-service
docker compose up -d

until docker compose exec mysql mysqladmin ping -h localhost -ulaw -plaw --silent; do
  echo "waiting for mysql..."
  sleep 2
done

mvn spring-boot:run
```

Health check:

```bash
curl http://localhost:8080/actuator/health
```

## 2) Import Legal Documents

Run while `law-service` is running:

```bash
curl -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current_new"
```

Expected totals:

- `metadataRows`: `127267`
- `contentRows`: `127267`
- `relationshipRows`: `651966`

Quick verify:

```bash
curl "http://localhost:8080/api/documents/4260"
```

## 3) Start RAG Service

```bash
cd /home/lee/Documents/LawAssistant/rag-service
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d
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

## 4) Optional UI Test

```bash
cd /home/lee/Documents/LawAssistant/UI_test
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8091
```

Open `http://localhost:8091`.

## Tests

Law service:

```bash
cd /home/lee/Documents/LawAssistant/law-service
mvn test
```

RAG service:

```bash
cd /home/lee/Documents/LawAssistant/rag-service
source .venv/bin/activate
pytest
```

## Data Notes

- Import input for `law-service`: `data_usable/current_new/`
- RAG tables: `data_usable/rag/`
- Canonical dataset workspace: `dataset/`

If you commit Parquet files to GitHub, use Git LFS.
