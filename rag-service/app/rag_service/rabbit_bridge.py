import json
import logging

import pika

from rag_service.config import get_settings
from rag_service.models import EmbeddingUpdateEvent
from rag_service.worker import index_document

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=settings.rabbitmq_embedding_queue, durable=True)
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
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    channel.basic_consume(queue=settings.rabbitmq_embedding_queue, on_message_callback=handle_message)
    logger.info("Consuming Law Service embedding events from %s", settings.rabbitmq_embedding_queue)
    channel.start_consuming()


if __name__ == "__main__":
    main()
