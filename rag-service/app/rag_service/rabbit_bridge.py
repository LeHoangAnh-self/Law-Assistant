import json
import logging
from datetime import UTC, datetime

import pika

from rag_service.config import get_settings
from rag_service.models import EmbeddingUpdateEvent
from rag_service.worker import index_document

logger = logging.getLogger(__name__)


def publish_failed_message(channel, failed_queue: str, source_queue: str, body: bytes) -> None:
    channel.basic_publish(
        exchange="",
        routing_key=failed_queue,
        body=json.dumps(
            {
                "failedAt": datetime.now(tz=UTC).isoformat(),
                "sourceQueue": source_queue,
                "body": body.decode("utf-8", errors="replace"),
            }
        ).encode("utf-8"),
        properties=pika.BasicProperties(delivery_mode=2),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    failed_queue = f"{settings.rabbitmq_embedding_queue}.failed"
    channel.queue_declare(queue=settings.rabbitmq_embedding_queue, durable=True)
    channel.queue_declare(queue=failed_queue, durable=True)
    channel.basic_qos(prefetch_count=10)

    def handle_message(ch, method, _properties, body: bytes) -> None:
        try:
            payload = json.loads(body)
            event = EmbeddingUpdateEvent.model_validate(payload)
            index_document.delay(event.documentId)
            logger.info("Queued indexing job for document %s", event.documentId)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception:
            logger.exception("Failed to process embedding update event")
            publish_failed_message(
                channel,
                failed_queue,
                settings.rabbitmq_embedding_queue,
                body,
            )
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(
        queue=settings.rabbitmq_embedding_queue,
        on_message_callback=handle_message,
    )
    logger.info("Consuming Law Service embedding events from %s", settings.rabbitmq_embedding_queue)
    channel.start_consuming()


if __name__ == "__main__":
    main()
