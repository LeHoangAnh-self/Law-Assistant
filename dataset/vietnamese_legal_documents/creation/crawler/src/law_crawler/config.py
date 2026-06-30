from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    user_agent: str
    timeout_seconds: int
    vbpl_api_base_url: str
    enable_pdf_ocr: bool
    pdf_ocr_backend: str
    pdf_ocr_lang: str
    pdf_ocr_device: str
    pdf_ocr_dpi: int
    pdf_text_min_chars: int
    thuvienphapluat_fallback_map_file: str | None
    thuvienphapluat_cookie_file: str | None


def load_settings() -> Settings:
    database_url = os.getenv("LAW_CRAWLER_DATABASE_URL")
    if not database_url:
        raise RuntimeError("LAW_CRAWLER_DATABASE_URL is required")

    timeout_raw = os.getenv("LAW_CRAWLER_TIMEOUT_SECONDS", "15")
    try:
        timeout_seconds = int(timeout_raw)
    except ValueError as exc:
        raise RuntimeError("LAW_CRAWLER_TIMEOUT_SECONDS must be an integer") from exc

    pdf_ocr_dpi_raw = os.getenv("LAW_CRAWLER_PDF_OCR_DPI", "250")
    try:
        pdf_ocr_dpi = int(pdf_ocr_dpi_raw)
    except ValueError as exc:
        raise RuntimeError("LAW_CRAWLER_PDF_OCR_DPI must be an integer") from exc

    pdf_text_min_chars_raw = os.getenv("LAW_CRAWLER_PDF_TEXT_MIN_CHARS", "200")
    try:
        pdf_text_min_chars = int(pdf_text_min_chars_raw)
    except ValueError as exc:
        raise RuntimeError("LAW_CRAWLER_PDF_TEXT_MIN_CHARS must be an integer") from exc

    return Settings(
        database_url=database_url,
        user_agent=os.getenv(
            "LAW_CRAWLER_USER_AGENT",
            "VN-Law-Advisor-Crawler/0.1",
        ),
        timeout_seconds=timeout_seconds,
        vbpl_api_base_url=os.getenv(
            "LAW_CRAWLER_VBPL_API_BASE_URL",
            "https://vbpl-bientap-gateway.moj.gov.vn/api",
        ).rstrip("/"),
        enable_pdf_ocr=os.getenv("LAW_CRAWLER_ENABLE_PDF_OCR", "").lower() in {"1", "true", "yes", "on"},
        pdf_ocr_backend=os.getenv("LAW_CRAWLER_PDF_OCR_BACKEND", "paddle_vietocr").lower(),
        pdf_ocr_lang=os.getenv("LAW_CRAWLER_PDF_OCR_LANG", "vie+eng"),
        pdf_ocr_device=os.getenv("LAW_CRAWLER_PDF_OCR_DEVICE", "cpu").lower(),
        pdf_ocr_dpi=max(100, min(pdf_ocr_dpi, 400)),
        pdf_text_min_chars=max(0, pdf_text_min_chars),
        thuvienphapluat_fallback_map_file=_optional_path(
            os.getenv(
                "LAW_CRAWLER_THUVIENPHAPLUAT_FALLBACK_MAP_FILE",
                "data_usable/thuvienphapluat_fallback_urls.csv",
            )
        ),
        thuvienphapluat_cookie_file=_optional_path(os.getenv("LAW_CRAWLER_THUVIENPHAPLUAT_COOKIE_FILE")),
    )


def _optional_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.exists():
        return None
    return str(path)
