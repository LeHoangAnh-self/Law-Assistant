from __future__ import annotations

import logging
import os
import re
from html import escape
from io import BytesIO
from typing import Any

from pypdf import PdfReader

from law_crawler.config import Settings


LOGGER = logging.getLogger(__name__)
ARTICLE_RE_FOR_PDF = re.compile(r"^[“\"]?Điều\s+[0-9]+[a-zA-Z]?\.?", re.IGNORECASE)
CLAUSE_RE_FOR_PDF = re.compile(r"^[0-9]+\.\s+")
POINT_RE_FOR_PDF = re.compile(r"^[a-zđ]\)\s+", re.IGNORECASE)
PAGE_NUMBER_RE = re.compile(r"^[0-9]{1,3}$")
SEPARATOR_RE = re.compile(r"^[_\-\s]{5,}$")
PREAMBLE_START_RE = re.compile(
    r"^(Căn\s+cứ|Theo\s+đề\s+nghị|Xét\s+đề\s+nghị|Bộ\s+trưởng|Chính\s+phủ|Ủy\s+ban)",
    re.IGNORECASE,
)


def extract_pdf_text_paragraphs(pdf_bytes: bytes) -> list[str]:
    reader = PdfReader(BytesIO(pdf_bytes))
    paragraphs: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        paragraphs.extend(split_pdf_text(text))
    return paragraphs


def extract_pdf_ocr_paragraphs(pdf_bytes: bytes, settings: Settings) -> list[str]:
    if settings.pdf_ocr_backend == "paddle_vietocr":
        return extract_pdf_paddle_vietocr_paragraphs(pdf_bytes, settings)
    if settings.pdf_ocr_backend == "tesseract":
        return extract_pdf_tesseract_paragraphs(pdf_bytes, settings)

    LOGGER.warning("Unsupported PDF OCR backend=%s", settings.pdf_ocr_backend)
    return []


def extract_pdf_tesseract_paragraphs(pdf_bytes: bytes, settings: Settings) -> list[str]:
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError as exc:
        LOGGER.warning("PDF OCR requested but pdf2image/pytesseract dependencies are not installed: %s", exc)
        return []

    paragraphs: list[str] = []
    try:
        images = convert_from_bytes(pdf_bytes, dpi=settings.pdf_ocr_dpi)
    except Exception:
        LOGGER.exception("Failed converting PDF pages to images for OCR")
        return []

    for page_number, image in enumerate(images, start=1):
        try:
            text = pytesseract.image_to_string(image, lang=settings.pdf_ocr_lang)
        except Exception:
            LOGGER.exception("Failed OCR for PDF page %s", page_number)
            continue
        paragraphs.extend(split_pdf_text(text))
    return paragraphs


def extract_pdf_paddle_vietocr_paragraphs(pdf_bytes: bytes, settings: Settings) -> list[str]:
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    try:
        from pdf2image import convert_from_bytes
        from paddleocr import PaddleOCR
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
    except ImportError as exc:
        LOGGER.warning("PaddleOCR/VietOCR PDF OCR requested but optional OCR dependencies are not installed: %s", exc)
        return []

    try:
        images = convert_from_bytes(pdf_bytes, dpi=settings.pdf_ocr_dpi)
    except Exception:
        LOGGER.exception("Failed converting PDF pages to images for PaddleOCR/VietOCR")
        return []

    try:
        detector = build_paddle_detector(PaddleOCR, settings)
        recognizer = build_vietocr_recognizer(Cfg, Predictor, settings)
    except Exception:
        LOGGER.exception("Failed initializing PaddleOCR/VietOCR")
        return []

    lines: list[str] = []
    for page_number, image in enumerate(images, start=1):
        try:
            page_boxes = detect_text_boxes(detector, image)
        except Exception:
            LOGGER.exception("Failed PaddleOCR text detection for PDF page %s", page_number)
            continue

        crops = []
        for box in sort_ocr_boxes_for_reading(page_boxes):
            crop = crop_box(image, box)
            if crop is None:
                continue
            crops.append(crop)
        if not crops:
            continue

        try:
            page_texts = recognizer.predict_batch(crops)
        except Exception:
            LOGGER.exception("Failed VietOCR batch text recognition for PDF page %s", page_number)
            continue

        for text in page_texts:
            normalized = clean_ocr_line(text)
            if normalized:
                lines.append(normalized)

    return split_pdf_text("\n".join(lines))


def build_paddle_detector(paddle_ocr_cls: Any, settings: Settings | None = None):
    device = settings.pdf_ocr_device if settings is not None else "cpu"
    candidates = [
        {
            "lang": "vi",
            "device": device,
            "enable_mkldnn": False,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
        },
        {"use_angle_cls": False, "lang": "vi", "det": True, "rec": False, "cls": False, "show_log": False},
        {"use_angle_cls": False, "lang": "vi", "det": True, "rec": False, "cls": False},
        {"use_angle_cls": False, "lang": "vi", "det": True, "rec": False},
    ]
    last_error = None
    for kwargs in candidates:
        try:
            return paddle_ocr_cls(**kwargs)
        except (TypeError, ValueError) as exc:
            last_error = exc
    raise last_error


def build_vietocr_recognizer(cfg_cls: Any, predictor_cls: Any, settings: Settings):
    config = cfg_cls.load_config_from_name("vgg_transformer")
    config["device"] = settings.pdf_ocr_device
    if "cnn" in config:
        config["cnn"]["pretrained"] = False
    return predictor_cls(config)


def detect_text_boxes(detector: Any, image: Any) -> list[list[tuple[float, float]]]:
    try:
        import numpy as np
    except ImportError:
        LOGGER.warning("PaddleOCR text detection requires numpy")
        return []

    image_array = np.array(image.convert("RGB"))
    try:
        result = detector.ocr(image_array)
    except (TypeError, ValueError):
        try:
            result = detector.ocr(image_array, det=True, rec=False, cls=False)
        except (TypeError, ValueError):
            result = detector.ocr(image_array, det=True, rec=False)
    return normalize_paddle_boxes(result)


def normalize_paddle_boxes(result: Any) -> list[list[tuple[float, float]]]:
    boxes: list[list[tuple[float, float]]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key in ("dt_polys", "rec_polys", "boxes"):
                if key in value:
                    visit(value[key])
                    return
            return
        if hasattr(value, "json"):
            json_value = value.json() if callable(value.json) else value.json
            visit(json_value)
            return
        if hasattr(value, "tolist"):
            visit(value.tolist())
            return
        if not isinstance(value, (list, tuple)) or not value:
            return
        if looks_like_box(value):
            boxes.append([(float(point[0]), float(point[1])) for point in value])
            return
        for item in value:
            visit(item)

    visit(result)
    return boxes


def looks_like_box(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return False
    for point in value[:4]:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return False
        try:
            float(point[0])
            float(point[1])
        except (TypeError, ValueError):
            return False
    return True


def sort_ocr_boxes_for_reading(boxes: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    if not boxes:
        return []

    line_heights = [max(1.0, box_bounds(box)[3] - box_bounds(box)[1]) for box in boxes]
    line_height = max(1.0, sum(line_heights) / len(line_heights))

    def key(box: list[tuple[float, float]]) -> tuple[int, float]:
        left, top, _, _ = box_bounds(box)
        return int((top + (line_height / 2)) / line_height), left

    return sorted(boxes, key=key)


def crop_box(image: Any, box: list[tuple[float, float]]):
    left, top, right, bottom = box_bounds(box)
    padding = max(2, int((bottom - top) * 0.12))
    left = max(0, int(left) - padding)
    top = max(0, int(top) - padding)
    right = min(image.width, int(right) + padding)
    bottom = min(image.height, int(bottom) + padding)
    if right <= left or bottom <= top:
        return None
    return image.crop((left, top, right, bottom))


def box_bounds(box: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in box]
    ys = [point[1] for point in box]
    return min(xs), min(ys), max(xs), max(ys)


def clean_ocr_line(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def paragraphs_to_html(paragraphs: list[str], *, source: str) -> str:
    html_paragraphs = [f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs]
    return f"<div id=\"toanvancontent\" data-source=\"{source}\">\n" + "\n".join(html_paragraphs) + "\n</div>"


def split_pdf_text(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    paragraphs: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            paragraphs.append(" ".join(current).strip())
            current.clear()

    for line in lines:
        if not line or PAGE_NUMBER_RE.match(line):
            flush()
            continue
        if SEPARATOR_RE.match(line):
            flush()
            continue
        starts_legal_block = bool(
            ARTICLE_RE_FOR_PDF.match(line)
            or CLAUSE_RE_FOR_PDF.match(line)
            or POINT_RE_FOR_PDF.match(line)
            or PREAMBLE_START_RE.match(line)
        )
        if starts_legal_block and current:
            flush()
        current.append(line)

    flush()
    return [paragraph for paragraph in paragraphs if paragraph]
