# Law Service

Spring Boot service for importing, storing, and serving Vietnamese legal documents.

## Features

- MySQL storage for metadata, content, and relationships
- Flyway schema migration
- Redis cache for document detail
- RabbitMQ embedding event publishing for RAG indexing

## Requirements

- Java 19+
- Maven
- Docker + Docker Compose

## Start Dependencies

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

## Run Service

```bash
export LAW_ADMIN_TOKEN=local-dev-admin-token
mvn spring-boot:run
```

Health check:

```bash
curl http://localhost:8080/actuator/health
```

RabbitMQ UI:

- URL: `http://localhost:15672`
- User: `law`
- Password: `law`

## Import Data

Importer expects these files in the source folder:

```text
metadata.parquet
content.parquet
relationships.parquet
```

Current import source:

```bash
curl -H "X-Admin-Token: $LAW_ADMIN_TOKEN" \
  -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current_new"
```

Compatibility source (older path):

```bash
curl -H "X-Admin-Token: $LAW_ADMIN_TOKEN" \
  -X POST "http://localhost:8080/api/imports/provided-data?sourceDirectory=../data_usable/current"
```

Verify imported record:

```bash
curl "http://localhost:8080/api/documents/4260"
```

Publish embedding events only after import check:

```bash
curl -H "X-Admin-Token: $LAW_ADMIN_TOKEN" \
  -X POST "http://localhost:8080/api/documents/embedding-events"
```

## API Examples

Search documents:

```bash
curl "http://localhost:8080/api/documents?page=0&size=20"
```

Document detail:

```bash
curl "http://localhost:8080/api/documents/4260"
```

Single-document embedding event:

```bash
curl -H "X-Admin-Token: $LAW_ADMIN_TOKEN" \
  -X POST "http://localhost:8080/api/documents/4260/embedding-events"
```

The import and embedding-event endpoints reject requests without `X-Admin-Token`.
For production-like profiles (`prod`, `production`, or `staging`) the service fails
fast if the admin token or DB/RabbitMQ credentials are missing or left at local
defaults such as `law`, `root`, or `password`.

## Reset Local State

This removes MySQL/Redis/RabbitMQ volumes:

```bash
cd /home/lee/Documents/LawAssistant/law-service
docker compose down -v
docker compose up -d
```

## Tests

```bash
mvn test
```
