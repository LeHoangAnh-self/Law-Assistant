# RAG Chat UI Test

Standalone test interface for the Law Assistant RAG service.

It serves a browser UI and proxies requests to the running RAG API, so the page can show the generated answer, rewritten query, classification, and source citations returned by `/api/rag/ask`.

## Features

- Chat UI for asking the local RAG service questions.
- Conversation context for follow-up questions in the same chat.
- Citation cards with retrieved passages and local document links.
- Local document reader with metadata, search, highlighted cited passage, and relationships.
- Optional OpenAI API key connection test from the UI.
- Exportable JSON log for response debugging.

## Run

Start the existing RAG service first:

```bash
cd ../rag-service
uvicorn rag_service.main:app --app-dir app --reload --port 8090
```

Then run this UI:

```bash
cd ../UI_test
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8091
```

Open:

```text
http://localhost:8091
```

If your RAG service is not on port `8090`, set:

```bash
export RAG_API_BASE_URL=http://localhost:8090
```

## ChatGPT / LLM Provider

This UI does not call ChatGPT directly. It calls the RAG service, and the RAG service calls the configured LLM provider.

For an OpenAI-compatible ChatGPT setup, configure the RAG service environment before starting `rag-service`, for example:

```bash
export LLM_PROVIDER=openai-compatible
export LLM_API_TYPE=responses
export LLM_API_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=your_api_key_here
export LLM_MODEL=gpt-5.5
export LLM_REASONING_EFFORT=medium
export LLM_MAX_OUTPUT_TOKENS=4096
```

Do not commit a real API key in this README. Put the real value in `../rag-service/.env`.

Use API model IDs such as `gpt-5.5`, not the product label `ChatGPT 5`.

If a model test fails, common causes are:

- the typed value is a ChatGPT product label instead of an API model ID
- the API key project does not have access to that model
- the RAG service was not restarted after changing `../rag-service/.env`
- the backend is still using `LLM_API_TYPE=chat_completions` instead of `responses`

For local testing without an external model, start `rag-service` with `LLM_PROVIDER=stub`.

The API key field in the UI is only for testing whether a key can reach OpenAI.
The backend endpoint is disabled by default; enable it only for local development:

```bash
export ENABLE_OPENAI_KEY_TEST=true
```

The key is not written to disk by `UI_test` and is not included in exported logs.

## Conversation Context

The UI proxy stores recent chat turns in memory and sends a contextualized question to the RAG service. This helps follow-up questions like "what about that document?" or "compare it with B" use the prior turns.

This memory is temporary. It resets when the UI server restarts or when you click `New chat`.

## Export Logs

Click `Export log` to download a JSON file containing:

- questions and answers
- contextualized questions sent to RAG
- citations and retrieved passages
- run settings
- health metadata

The export intentionally excludes the API key value.
