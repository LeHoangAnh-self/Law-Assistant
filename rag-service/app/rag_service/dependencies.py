from functools import lru_cache

from rag_service.config import get_settings
from rag_service.law_client import LawServiceClient
from rag_service.pipeline import RagPipeline


@lru_cache
def get_rag_pipeline() -> RagPipeline:
    return RagPipeline(get_settings())


@lru_cache
def get_law_service_client() -> LawServiceClient:
    settings = get_settings()
    return LawServiceClient(
        str(settings.law_service_base_url),
        admin_token=settings.law_service_admin_token,
    )
