from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


def configure_observability(app: FastAPI) -> None:
    FastAPIInstrumentor.instrument_app(app)
