from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rag_service.config import get_settings
from rag_service.dependencies import get_law_service_client, get_rag_pipeline
from rag_service.law_client import LawServiceClient
from rag_service.models import AskRequest, AskResponse, HealthResponse
from rag_service.observability import configure_observability
from rag_service.pipeline import RagPipeline

settings = get_settings()
app = FastAPI(title="Law Assistant RAG Service", version="0.1.0")
configure_observability(app)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


@app.get("/documents", response_class=FileResponse)
async def document_picker() -> FileResponse:
    return FileResponse(STATIC_DIR / "documents.html")


@app.get("/api/documents")
async def search_documents(
    law_client: Annotated[LawServiceClient, Depends(get_law_service_client)],
    query: str = "",
    document_type: str | None = Query(default=None, alias="documentType"),
    validity_status: str | None = Query(default=None, alias="validityStatus"),
    scope: str | None = None,
    issuing_authority: str | None = Query(default=None, alias="issuingAuthority"),
    external_docid: str | None = Query(default=None, alias="externalDocid"),
    issued_date_from: str | None = Query(default=None, alias="issuedDateFrom"),
    issued_date_to: str | None = Query(default=None, alias="issuedDateTo"),
    effective_date_from: str | None = Query(default=None, alias="effectiveDateFrom"),
    effective_date_to: str | None = Query(default=None, alias="effectiveDateTo"),
    expired_date_from: str | None = Query(default=None, alias="expiredDateFrom"),
    expired_date_to: str | None = Query(default=None, alias="expiredDateTo"),
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> dict:
    return await law_client.search_documents(
        query=query,
        page=page,
        size=size,
        document_type=document_type,
        validity_status=validity_status,
        scope=scope,
        issuing_authority=issuing_authority,
        external_docid=external_docid,
        issued_date_from=issued_date_from,
        issued_date_to=issued_date_to,
        effective_date_from=effective_date_from,
        effective_date_to=effective_date_to,
        expired_date_from=expired_date_from,
        expired_date_to=expired_date_to,
    )


@app.get("/api/documents/{document_id}")
async def get_document_detail(
    document_id: int,
    law_client: Annotated[LawServiceClient, Depends(get_law_service_client)],
) -> dict:
    return await law_client.get_document_detail(document_id)


@app.post("/api/rag/ask", response_model=AskResponse)
async def ask(
    request: AskRequest,
    pipeline: Annotated[RagPipeline, Depends(get_rag_pipeline)],
) -> AskResponse:
    return await pipeline.ask(request)
