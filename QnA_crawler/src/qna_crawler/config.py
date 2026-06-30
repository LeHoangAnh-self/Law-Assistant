from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    document_database_url: str | None
    user_agent: str
    timeout_seconds: int


def load_settings() -> Settings:
    database_url = os.getenv("QNA_CRAWLER_DATABASE_URL") or os.getenv("LAW_CRAWLER_DATABASE_URL")
    if not database_url:
        raise RuntimeError("QNA_CRAWLER_DATABASE_URL is required")

    timeout_raw = os.getenv("QNA_CRAWLER_TIMEOUT_SECONDS", os.getenv("LAW_CRAWLER_TIMEOUT_SECONDS", "15"))
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise RuntimeError("QNA_CRAWLER_TIMEOUT_SECONDS must be an integer") from exc

    return Settings(
        database_url=database_url,
        document_database_url=os.getenv("QNA_CRAWLER_DOCUMENT_DATABASE_URL"),
        user_agent=os.getenv("QNA_CRAWLER_USER_AGENT", "VN-Law-QnA-Crawler/0.1"),
        timeout_seconds=timeout_seconds,
    )
