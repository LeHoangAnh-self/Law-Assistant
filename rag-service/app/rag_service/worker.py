from celery import Celery
import httpx
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from rag_service.config import get_settings
from rag_service.indexing import DocumentIndexer

settings = get_settings()

celery_app = Celery(
    "rag_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)

_indexer: DocumentIndexer | None = None


def get_indexer() -> DocumentIndexer:
    global _indexer
    if _indexer is None:
        _indexer = DocumentIndexer(settings)
    return _indexer


@celery_app.task(
    name="rag_service.index_document",
    autoretry_for=(
        ResponseHandlingException,
        UnexpectedResponse,
        httpx.ConnectError,
        httpx.RemoteProtocolError,
        httpx.ReadTimeout,
        TimeoutError,
        ConnectionError,
    ),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=8,
)
def index_document(document_id: int) -> int:
    return get_indexer().index_document(document_id)
