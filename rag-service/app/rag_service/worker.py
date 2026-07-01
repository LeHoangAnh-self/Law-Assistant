import logging

from celery import Celery
from celery.app.task import Task

from rag_service.config import get_settings
from rag_service.indexing import RETRYABLE_INDEXING_EXCEPTIONS, DocumentIndexer
from rag_service.law_client import LawServiceClient

settings = get_settings()
logger = logging.getLogger(__name__)

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


def _task_document_id(args: tuple, kwargs: dict) -> int | None:
    if args:
        return int(args[0])
    document_id = kwargs.get("document_id")
    if document_id is None:
        return None
    return int(document_id)


def _update_document_status(document_id: int, status: str) -> None:
    client = LawServiceClient(
        str(settings.law_service_base_url),
        admin_token=settings.law_service_admin_token,
    )
    client.update_embedding_status_sync(document_id, status)


class IndexDocumentTask(Task):
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        document_id = _task_document_id(args, kwargs)
        if document_id is not None:
            try:
                _update_document_status(document_id, "PENDING")
            except Exception:
                logger.warning(
                    "Failed to mark document %s PENDING after scheduling retry",
                    document_id,
                    exc_info=True,
                )
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        document_id = _task_document_id(args, kwargs)
        if document_id is not None:
            try:
                _update_document_status(document_id, "FAILED")
            except Exception:
                logger.warning(
                    "Failed to mark document %s FAILED after task failure",
                    document_id,
                    exc_info=True,
                )
        super().on_failure(exc, task_id, args, kwargs, einfo)


def get_indexer() -> DocumentIndexer:
    global _indexer
    if _indexer is None:
        _indexer = DocumentIndexer(settings)
    return _indexer


@celery_app.task(
    name="rag_service.index_document",
    base=IndexDocumentTask,
    autoretry_for=RETRYABLE_INDEXING_EXCEPTIONS,
    retry_backoff=10,
    retry_backoff_max=300,
    retry_jitter=False,
    max_retries=8,
)
def index_document(document_id: int) -> int:
    return get_indexer().index_document(document_id)
