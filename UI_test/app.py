import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


RAG_API_BASE_URL = os.getenv("RAG_API_BASE_URL", "http://localhost:8090").rstrip("/")
ENABLE_OPENAI_KEY_TEST = os.getenv("ENABLE_OPENAI_KEY_TEST", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_HISTORY_MESSAGES = 10
MAX_CONTEXT_CHARS = 2600

app = FastAPI(title="Law Assistant RAG UI Test", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
CONVERSATIONS: dict[str, list[dict[str, Any]]] = {}


class AskPayload(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    top_k: int = Field(default=6, ge=1, le=20)
    filters: dict[str, str] = Field(default_factory=dict)
    retrieval_cutoff_date: str | None = None
    conversation_id: str | None = None
    include_context: bool = True


class OpenAiTestPayload(BaseModel):
    api_key: str = Field(min_length=20, max_length=300)
    model: str = Field(default="gpt-5.5", min_length=1, max_length=100)
    reasoning_effort: str = Field(default="medium", min_length=1, max_length=20)


def _trim(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}..."


def _build_conversation_context(history: list[dict[str, Any]]) -> str | None:
    if not history:
        return None

    context_lines: list[str] = []
    for item in history[-MAX_HISTORY_MESSAGES:]:
        role = "Người dùng" if item.get("role") == "user" else "Trợ lý"
        content = _trim(str(item.get("content", "")), 520)
        if content:
            context_lines.append(f"{role}: {content}")

    context = "\n".join(context_lines)
    return context[-MAX_CONTEXT_CHARS:] or None


def _safe_http_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return url
    return None


def _sanitize_document_source_url(data: dict[str, Any]) -> dict[str, Any]:
    document = data.get("document")
    if not isinstance(document, dict):
        return data

    original = document.get("sourceUrl") or document.get("source_url")
    safe_url = _safe_http_url(original)
    if safe_url:
        document["sourceUrl"] = safe_url
        return data

    document.pop("sourceUrl", None)
    document.pop("source_url", None)
    if original:
        document["sourceUrlText"] = str(original)
    return data


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/documents/{document_id}")
async def document_page(document_id: int) -> FileResponse:
    return FileResponse(STATIC_DIR / "document.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{RAG_API_BASE_URL}/health")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach RAG service at {RAG_API_BASE_URL}: {exc}",
        ) from exc

    return {
        "ui": "ok",
        "rag_api_base_url": RAG_API_BASE_URL,
        "rag": response.json(),
    }


@app.get("/api/documents/{document_id}")
async def get_document(document_id: int) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(f"{RAG_API_BASE_URL}/api/documents/{document_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach RAG service at {RAG_API_BASE_URL}: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    return _sanitize_document_source_url(response.json())


@app.post("/api/openai/test")
async def test_openai_connection(payload: OpenAiTestPayload) -> dict[str, Any]:
    if not ENABLE_OPENAI_KEY_TEST:
        raise HTTPException(
            status_code=403,
            detail="OpenAI key test is disabled. Set ENABLE_OPENAI_KEY_TEST=true for local dev.",
        )

    headers = {
        "Authorization": f"Bearer {payload.api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": payload.model,
        "input": [{"role": "user", "content": "Reply with OK."}],
        "reasoning": {"effort": payload.reasoning_effort},
        "max_output_tokens": 64,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI connection failed: {exc}") from exc

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    data = response.json()
    output_text = data.get("output_text", "")
    if not output_text:
        for item in data.get("output", []):
            for content in item.get("content", []):
                if content.get("text"):
                    output_text = content["text"]
                    break
    return {
        "status": "ok",
        "model": data.get("model", payload.model),
        "response": output_text.strip(),
    }


@app.delete("/api/conversations/{conversation_id}")
async def clear_conversation(conversation_id: str) -> dict[str, Any]:
    CONVERSATIONS.pop(conversation_id, None)
    return {"status": "cleared", "conversation_id": conversation_id}


@app.post("/api/ask")
async def ask(payload: AskPayload) -> dict[str, Any]:
    conversation_id = payload.conversation_id or str(uuid4())
    history = CONVERSATIONS.setdefault(conversation_id, [])
    conversation_context = (
        _build_conversation_context(history)
        if payload.include_context
        else None
    )
    request_body = payload.model_dump(
        exclude={"conversation_id", "include_context"},
        exclude_none=True,
    )
    request_body["question"] = payload.question
    if conversation_context:
        request_body["conversation_context"] = conversation_context
    if not request_body.get("filters"):
        request_body.pop("filters", None)

    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{RAG_API_BASE_URL}/api/rag/ask", json=request_body)
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach RAG service at {RAG_API_BASE_URL}: {exc}",
        ) from exc

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)

    data = response.json()
    history.append({"role": "user", "content": payload.question})
    history.append(
        {
            "role": "assistant",
            "content": data.get("answer", ""),
            "references": data.get("references", []),
        }
    )
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[: len(history) - MAX_HISTORY_MESSAGES]

    data["conversation_id"] = conversation_id
    data["original_question"] = payload.question
    data["contextual_question"] = (
        f"{conversation_context}\n\nCâu hỏi hiện tại: {payload.question}"
        if conversation_context
        else payload.question
    )
    data["conversation_context"] = conversation_context
    data["used_context"] = bool(conversation_context)
    return data
