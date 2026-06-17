# Law Service

Spring Boot service for importing, storing, and serving Vietnamese legal documents.

It provides:

- MySQL storage for legal metadata, HTML content, extracted text, and document relationships
- Flyway-managed database schema
- Redis-backed caching for document detail responses
- RabbitMQ embedding events for asynchronous RAG indexing
- REST APIs for document search, document detail, imports, and embedding event publishing

## Requirements

- Java 19
- Maven
- Docker and Docker Compose

## Local Start

Start MySQL, Redis, and RabbitMQ:

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

Run the service:

```bash
mvn spring-boot:run
```

Health check:

```bash
curl "http://localhost:8080/actuator/health"
```

RabbitMQ management UI:

- URL: `http://localhost:15672`
- Username: `law`
- Password: `law`

## Reset From Scratch

This removes local MySQL, Redis, and RabbitMQ volumes:

```bash
cd /home/lee/Documents/LawAssistant/law-service
docker compose down -v
docker compose up -d
```

Then wait for MySQL and start the service:

```bash
until docker compose exec mysql mysqladmin ping -h localhost -ulaw -plaw --silent; do
  echo "waiting for mysql..."
  sleep 2
done

mvn spring-boot:run
```

## Import Cleaned Data

The importer expects a directory with exactly these files:

```text
metadata.parquet
content.parquet
relationships.parquet
```

Use the prepared dataset at `../data_usable/current`:

```bash
curl -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current"
```

Expected result:

```json
{
  "metadataRows": 127267,
  "contentRows": 127267,
  "relationshipRows": 651966,
  "publishEmbeddingEvents": false
}
```

Verify an imported document:

```bash
curl "http://localhost:8080/api/documents/4260"
```

Only publish embedding events after the database import has been verified:

```bash
curl -X POST "http://localhost:8080/api/documents/embedding-events"
```

## API Examples

Search documents:

```bash
curl "http://localhost:8080/api/documents?page=0&size=20"
```

Get document detail:

```bash
curl "http://localhost:8080/api/documents/4260"
```

Request one embedding update:

```bash
curl -X POST "http://localhost:8080/api/documents/4260/embedding-events"
```

Import data:

```bash
curl -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current"
```

## Tests

```bash
mvn test
```

## Troubleshooting

If startup fails with `Communications link failure`, MySQL is not ready yet. Run:

```bash
docker compose ps
docker compose logs mysql --tail=80
```

If port `3306` is already in use:

```bash
ss -ltnp | grep ':3306'
```

Stop the conflicting local MySQL process or change the MySQL port mapping in `docker-compose.yml`.
