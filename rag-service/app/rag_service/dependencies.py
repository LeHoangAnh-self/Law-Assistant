from functools import lru_cache

from rag_service.config import get_settings
from rag_service.law_client import LawServiceClient
from rag_service.pipeline import RagPipeline


@lru_cache
def get_rag_pipeline() -> RagPipeline:
    return RagPipeline(get_settings())


@lru_cache
def get_law_service_client() -> LawServiceClient:
    return LawServiceClient(str(get_settings().law_service_base_url))
