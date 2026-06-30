from __future__ import annotations

import argparse
import html
import json
import re
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import pyarrow.parquet as pq

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - exercised when tqdm is not installed.
    tqdm = None


DEFAULT_DATA_DIR = Path("data_usable/current")
CONTEXT_COLUMNS = [
    "document_id",
    "context_type",
    "stable_anchor",
    "order_index",
    "article_number",
    "clause_number",
    "point_label",
    "heading",
    "content_text",
    "content_html",
]


@dataclass(frozen=True)
class Dataset:
    metadata: list[dict[str, Any]]
    metadata_by_document: dict[int, dict[str, Any]]
    context_path: Path
    pdf_review_by_document: dict[int, dict[str, Any]]
    context_cache: dict[int, list[dict[str, Any]]]
    stats: dict[str, Any]


def main() -> int:
    parser = argparse.ArgumentParser(description="Browse exported VN law dataset documents in a local UI.")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="Directory containing exported Parquet files.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the browser after starting the server.")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    dataset = load_dataset(data_dir)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(dataset, data_dir))
    url = f"http://{args.host}:{args.port}"
    print(f"Preview UI: {url}")
    print(f"Dataset: {data_dir.resolve()}")
    print("Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


def load_dataset(data_dir: Path) -> Dataset:
    metadata_path = data_dir / "metadata.parquet"
    context_path = data_dir / "context.parquet"
    pdf_review_path = data_dir / "pdf_review.parquet"

    if not metadata_path.exists():
        raise SystemExit(f"Missing {metadata_path}")
    if not context_path.exists():
        raise SystemExit(f"Missing {context_path}")

    metadata = _read_parquet_records(metadata_path, desc="Loading metadata")
    metadata_by_document = {
        int(row["document_id"]): row
        for row in metadata
        if row.get("document_id") is not None
    }
    pdf_review_records = _read_parquet_records(pdf_review_path, desc="Loading PDF review") if pdf_review_path.exists() else []
    pdf_review_by_document = {
        int(row["document_id"]): row
        for row in pdf_review_records
        if row.get("document_id") is not None
    }
    context_rows = pq.ParquetFile(context_path).metadata.num_rows

    stats = {
        "documents": len(metadata),
        "context_rows": context_rows,
        "pdf_review": len(pdf_review_records),
        "document_types": _facet(metadata, "document_type"),
        "authorities": _facet(metadata, "issuing_authority"),
        "statuses": _facet(metadata, "validity_status"),
    }

    return Dataset(
        metadata=metadata,
        metadata_by_document=metadata_by_document,
        context_path=context_path,
        pdf_review_by_document=pdf_review_by_document,
        context_cache={},
        stats=stats,
    )


def _read_parquet_records(
    path: Path,
    *,
    columns: list[str] | None = None,
    desc: str | None = None,
) -> list[dict[str, Any]]:
    parquet_file = pq.ParquetFile(path)
    row_group_indices = range(parquet_file.metadata.num_row_groups)
    rows: list[dict[str, Any]] = []
    for row_group_index in _progress(row_group_indices, desc=desc or f"Loading {path.name}"):
        table = parquet_file.read_row_group(row_group_index, columns=columns)
        rows.extend({key: _jsonable(value) for key, value in row.items()} for row in table.to_pylist())
    return rows


def _progress(items: Iterable[int], *, desc: str) -> Iterable[int]:
    if tqdm is None:
        print(f"{desc}...", file=sys.stderr)
        return items
    return tqdm(items, desc=desc, unit="row-group", leave=False)


def load_document_context(dataset: Dataset, document_id: int) -> list[dict[str, Any]]:
    cached = dataset.context_cache.get(document_id)
    if cached is not None:
        return cached

    parquet_file = pq.ParquetFile(dataset.context_path)
    document_id_column = parquet_file.schema_arrow.get_field_index("document_id")
    if document_id_column < 0:
        raise SystemExit(f"Missing document_id column in {dataset.context_path}")

    row_group_indices = _matching_row_groups(parquet_file, document_id_column, document_id)
    rows: list[dict[str, Any]] = []
    for row_group_index in row_group_indices:
        table = parquet_file.read_row_group(row_group_index, columns=CONTEXT_COLUMNS)
        for row in table.to_pylist():
            if _as_int(row.get("document_id")) == document_id:
                row = {key: _jsonable(value) for key, value in row.items()}
                row["sort_key"] = _sort_key(row)
                rows.append(row)

    rows.sort(key=lambda item: item.get("sort_key") or (999999, ""))
    dataset.context_cache[document_id] = rows
    return rows


def _matching_row_groups(parquet_file: pq.ParquetFile, column_index: int, document_id: int) -> list[int]:
    matches: list[int] = []
    for row_group_index in range(parquet_file.metadata.num_row_groups):
        column = parquet_file.metadata.row_group(row_group_index).column(column_index)
        statistics = column.statistics
        if statistics is None or statistics.min is None or statistics.max is None:
            matches.append(row_group_index)
            continue
        if int(statistics.min) <= document_id <= int(statistics.max):
            matches.append(row_group_index)
    return matches


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_key(row: dict[str, Any]) -> tuple[int, str]:
    order_index = _as_int(row.get("order_index"))
    if order_index is None:
        order_index = 999999
    return (order_index, str(row.get("stable_anchor") or ""))


def _facet(rows: list[dict[str, Any]], column: str) -> list[str]:
    values = sorted({str(row[column]) for row in rows if row.get(column)})
    return values


def make_handler(dataset: Dataset, data_dir: Path) -> type[BaseHTTPRequestHandler]:
    class PreviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_text(INDEX_HTML, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/stats":
                self._send_json({"data_dir": str(data_dir.resolve()), **dataset.stats})
                return
            if parsed.path == "/api/documents":
                self._send_json(search_documents(dataset, parse_qs(parsed.query)))
                return
            match = re.fullmatch(r"/api/document/(\d+)", parsed.path)
            if match:
                document = get_document(dataset, int(match.group(1)))
                if document is None:
                    self._send_json({"error": "Document not found"}, HTTPStatus.NOT_FOUND)
                else:
                    self._send_json(document)
                return
            self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send_text(json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8", status)

        def _send_text(
            self,
            text: str,
            content_type: str,
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return PreviewHandler


def search_documents(dataset: Dataset, query: dict[str, list[str]]) -> dict[str, Any]:
    q = _first(query, "q").lower()
    doc_type = _first(query, "type")
    authority = _first(query, "authority")
    status = _first(query, "status")
    limit = max(1, min(100, _as_int(_first(query, "limit")) or 40))
    offset = max(0, _as_int(_first(query, "offset")) or 0)

    results = []
    for row in dataset.metadata:
        haystack = " ".join(
            str(row.get(field) or "")
            for field in ("title", "document_number", "document_type", "issuing_authority", "validity_status")
        ).lower()
        if q and q not in haystack:
            continue
        if doc_type and row.get("document_type") != doc_type:
            continue
        if authority and row.get("issuing_authority") != authority:
            continue
        if status and row.get("validity_status") != status:
            continue
        results.append(compact_metadata(row))

    results.sort(key=lambda row: (row.get("effective_date") or "", row.get("title") or ""), reverse=True)
    page = results[offset : offset + limit]
    return {"total": len(results), "offset": offset, "limit": limit, "documents": page}


def get_document(dataset: Dataset, document_id: int) -> dict[str, Any] | None:
    metadata = _jsonable_dict(dataset.metadata_by_document.get(document_id))
    if metadata is None:
        return None

    context_rows = load_document_context(dataset, document_id)
    sections = []
    for row in context_rows:
        if row.get("context_type") == "DOCUMENT":
            continue
        sections.append(
            {
                "context_type": row.get("context_type"),
                "stable_anchor": row.get("stable_anchor"),
                "heading": row.get("heading"),
                "content_text": row.get("content_text"),
                "article_number": row.get("article_number"),
                "clause_number": row.get("clause_number"),
                "point_label": row.get("point_label"),
            }
        )

    pdf_review = dataset.pdf_review_by_document.get(document_id)
    document_row = next((row for row in context_rows if row.get("context_type") == "DOCUMENT"), None)
    document_html = str(document_row.get("content_html") or "") if document_row else ""
    if not document_html and pdf_review:
        document_html = pdf_review.get("extracted_html") or _paragraphize(pdf_review.get("extracted_text") or "")

    return {
        "metadata": metadata,
        "sections": sections,
        "document_html": wrap_document_html(document_html or _paragraphize(_document_text(context_rows))),
        "pdf_review": _jsonable_dict(pdf_review) if pdf_review else None,
    }


def compact_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": row.get("document_id"),
        "title": row.get("title"),
        "document_number": row.get("document_number"),
        "document_type": row.get("document_type"),
        "issuing_authority": row.get("issuing_authority"),
        "issued_date": row.get("issued_date"),
        "effective_date": row.get("effective_date"),
        "expired_date": row.get("expired_date"),
        "validity_status": row.get("validity_status"),
        "source_url": row.get("source_url"),
    }


def _jsonable_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: _jsonable(value) for key, value in row.items()}


def _document_text(context_rows: list[dict[str, Any]]) -> str:
    document_row = next((row for row in context_rows if row.get("context_type") == "DOCUMENT"), None)
    if document_row:
        return str(document_row.get("content_text") or "")
    return "\n\n".join(str(row.get("content_text") or "") for row in context_rows[:200])


def _paragraphize(text: str) -> str:
    paragraphs = [f"<p>{html.escape(part.strip())}</p>" for part in re.split(r"\n{2,}", text) if part.strip()]
    return "\n".join(paragraphs) or "<p>No preview content available.</p>"


def wrap_document_html(document_html: str) -> str:
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    color-scheme: light;
    --ink: #182427;
    --muted: #647174;
    --rule: #d8ddd6;
    --paper: #fffdf8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: #edece6;
    color: var(--ink);
    font-family: "Times New Roman", "Noto Serif", serif;
    font-size: 17px;
    line-height: 1.68;
  }}
  main {{
    max-width: 860px;
    min-height: 100vh;
    margin: 0 auto;
    padding: 52px 64px 76px;
    background: var(--paper);
    box-shadow: 0 0 0 1px rgba(33, 47, 54, 0.08), 0 26px 80px rgba(33, 47, 54, 0.14);
  }}
  p {{ margin: 0 0 13px; }}
  table {{
    width: 100% !important;
    border-collapse: collapse;
    margin: 18px 0;
    font-size: .95em;
  }}
  td, th {{
    padding: 8px 10px;
    vertical-align: top;
    border-color: var(--rule) !important;
  }}
  img {{ max-width: 100%; }}
  h1, h2, h3 {{
    line-height: 1.25;
    margin: 1.35em 0 .55em;
  }}
  a {{ color: #0c5c70; }}
  strong, b {{ color: #11191b; }}
  [style*="font-size"], [style*="width"] {{ max-width: 100%; }}
  .doc-waterline {{
    border-top: 1px solid var(--rule);
    color: var(--muted);
    font-family: Arial, sans-serif;
    font-size: 12px;
    margin-top: 42px;
    padding-top: 14px;
  }}
  @media (max-width: 720px) {{
    body {{ font-size: 16px; background: var(--paper); }}
    main {{ padding: 26px 20px 48px; box-shadow: none; }}
  }}
</style>
</head>
<body><main>{document_html}<div class="doc-waterline">Local dataset preview</div></main></body>
</html>"""


def _first(query: dict[str, list[str]], name: str) -> str:
    value = query.get(name, [""])[0]
    return value.strip()


INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>VN Law Dataset Preview</title>
<style>
  :root {
    --bg: #eef1ed;
    --panel: #ffffff;
    --panel-soft: #f8faf7;
    --paper: #fffdf8;
    --text: #1b282b;
    --muted: #667376;
    --line: #dce3dc;
    --accent: #146c79;
    --accent-strong: #0a5260;
    --accent-soft: #e8f4f3;
    --mark: #f6c85f;
    --danger: #b95b44;
    --shadow: 0 18px 50px rgba(25, 37, 41, .10);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
  }
  button, input, select { font: inherit; }
  button {
    border: 1px solid var(--line);
    background: var(--panel);
    color: var(--text);
    border-radius: 6px;
    min-height: 36px;
    padding: 7px 10px;
    cursor: pointer;
  }
  button:hover { border-color: #aab8ae; background: #fbfcfb; }
  button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .shell {
    display: grid;
    grid-template-columns: minmax(340px, 430px) minmax(0, 1fr);
    min-height: 100vh;
  }
  aside {
    border-right: 1px solid var(--line);
    background: var(--panel);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }
  header {
    padding: 18px 18px 14px;
    border-bottom: 1px solid var(--line);
  }
  h1 {
    margin: 0 0 4px;
    font-size: 18px;
    letter-spacing: 0;
  }
  .stats {
    color: var(--muted);
    font-size: 13px;
  }
  .stats strong {
    color: var(--text);
    font-weight: 750;
  }
  .filters {
    display: grid;
    gap: 8px;
    margin-top: 14px;
  }
  .search {
    position: relative;
  }
  .search input {
    width: 100%;
    min-height: 40px;
    padding: 9px 10px 9px 34px;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--panel-soft);
    color: var(--text);
  }
  .search svg {
    position: absolute;
    left: 10px;
    top: 10px;
    width: 18px;
    height: 18px;
    color: var(--muted);
  }
  .filter-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  select {
    width: 100%;
    min-height: 36px;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--panel-soft);
    color: var(--text);
    padding: 7px 8px;
  }
  .list-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 18px;
    color: var(--muted);
    font-size: 13px;
    border-bottom: 1px solid var(--line);
  }
  .tiny-button {
    min-height: 30px;
    padding: 5px 9px;
    font-size: 12px;
  }
  .doc-list {
    overflow: auto;
    flex: 1;
  }
  .doc-card {
    display: block;
    width: 100%;
    text-align: left;
    border: 0;
    border-bottom: 1px solid var(--line);
    border-radius: 0;
    padding: 14px 18px;
    background: var(--panel);
  }
  .doc-card.active {
    background: var(--accent-soft);
    box-shadow: inset 3px 0 0 var(--accent);
  }
  .doc-title {
    font-weight: 700;
    font-size: 14px;
    line-height: 1.35;
    margin-bottom: 7px;
  }
  .doc-fields {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    color: var(--muted);
    font-size: 12px;
  }
  .doc-date {
    color: var(--accent-strong);
    font-weight: 700;
  }
  .pill {
    border: 1px solid var(--line);
    background: var(--panel-soft);
    border-radius: 999px;
    padding: 3px 7px;
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .workspace {
    min-width: 0;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr);
    background: #f7f8f5;
  }
  .doc-top {
    background: var(--panel);
    border-bottom: 1px solid var(--line);
    padding: 20px 24px;
  }
  .doc-heading {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 16px;
  }
  h2 {
    margin: 0 0 8px;
    font-size: 23px;
    line-height: 1.22;
    letter-spacing: 0;
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: end;
  }
  .source-link {
    color: var(--accent-strong);
    text-decoration: none;
    white-space: nowrap;
    font-size: 13px;
    font-weight: 650;
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 8px 10px;
    background: var(--panel-soft);
  }
  .source-link:hover { border-color: #aab8ae; background: white; }
  .meta-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(120px, 1fr));
    gap: 8px;
    margin-top: 12px;
  }
  .meta-item {
    border: 1px solid var(--line);
    background: var(--panel-soft);
    border-radius: 6px;
    padding: 8px 9px;
    min-width: 0;
  }
  .label {
    color: var(--muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .04em;
    margin-bottom: 3px;
  }
  .value {
    font-size: 13px;
    font-weight: 650;
    overflow-wrap: anywhere;
  }
  .doc-body {
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(260px, 340px) minmax(0, 1fr);
  }
  .outline {
    border-right: 1px solid var(--line);
    background: #fbfcfa;
    min-height: 0;
    overflow: auto;
    padding: 14px;
  }
  .outline-title {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 10px;
  }
  .outline-title strong { font-size: 13px; }
  .section-list {
    display: grid;
    gap: 7px;
  }
  .section-card {
    border: 1px solid var(--line);
    border-radius: 6px;
    padding: 9px 10px;
    background: var(--panel);
  }
  .section-card:hover { border-color: #b7c4bb; }
  .section-card mark {
    background: color-mix(in srgb, var(--mark) 52%, transparent);
    border-radius: 3px;
    padding: 0 2px;
  }
  .section-anchor {
    color: var(--accent-strong);
    font-size: 12px;
    font-weight: 750;
    margin-bottom: 4px;
  }
  .section-type {
    color: var(--muted);
    font-size: 11px;
    font-weight: 650;
    text-transform: uppercase;
    letter-spacing: .04em;
  }
  .section-text {
    color: #3e4c51;
    font-size: 12px;
    line-height: 1.45;
    max-height: 96px;
    overflow: hidden;
  }
  .preview {
    min-height: 0;
    padding: 18px;
  }
  iframe {
    display: block;
    width: 100%;
    height: 100%;
    min-height: 420px;
    border: 1px solid var(--line);
    border-radius: 6px;
    background: var(--paper);
    box-shadow: var(--shadow);
  }
  .empty {
    display: grid;
    place-items: center;
    min-height: 100vh;
    color: var(--muted);
    text-align: center;
    padding: 24px;
  }
  .banner {
    margin-top: 10px;
    border: 1px solid #e2b5a8;
    background: #fff5f1;
    color: var(--danger);
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
  }
  .hint {
    color: var(--muted);
    font-size: 12px;
    margin-top: 8px;
  }
  @media (max-width: 980px) {
    .shell { grid-template-columns: 1fr; }
    aside { min-height: auto; max-height: 48vh; border-right: 0; border-bottom: 1px solid var(--line); }
    .workspace { min-height: 70vh; }
    .doc-body { grid-template-columns: 1fr; }
    .outline { max-height: 260px; border-right: 0; border-bottom: 1px solid var(--line); }
    .meta-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .doc-heading { display: block; }
    .actions { justify-content: start; margin-top: 10px; }
    .source-link { display: inline-block; }
    iframe { min-height: 70vh; }
  }
</style>
</head>
<body>
<div class="shell">
  <aside>
    <header>
      <h1>VN Law Dataset Preview</h1>
      <div class="stats" id="stats">Loading dataset...</div>
      <div class="hint">Search covers title, number, type, authority, and status.</div>
      <div class="filters">
        <label class="search" aria-label="Search documents">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"></circle><path d="m21 21-4.3-4.3"></path></svg>
          <input id="q" placeholder="Search title, number, authority" autocomplete="off">
        </label>
        <div class="filter-grid">
          <select id="type" aria-label="Document type"><option value="">All types</option></select>
          <select id="status" aria-label="Validity status"><option value="">All statuses</option></select>
        </div>
        <select id="authority" aria-label="Issuing authority"><option value="">All authorities</option></select>
      </div>
    </header>
    <div class="list-meta">
      <span id="result-count">0 documents</span>
      <button class="tiny-button" id="clear">Clear</button>
    </div>
    <div class="doc-list" id="documents"></div>
  </aside>
  <main class="workspace" id="workspace">
    <div class="empty">Select a document to preview full text and structured sections.</div>
  </main>
</div>
<script>
const state = { documents: [], activeId: null, searchTimer: null };
const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  }[ch]));
}

function compact(value) {
  return value ? escapeHtml(value) : "—";
}

function optionList(select, values, label) {
  select.innerHTML = `<option value="">${label}</option>` + values.map((value) =>
    `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`
  ).join("");
}

async function boot() {
  const stats = await fetch("/api/stats").then((r) => r.json());
  $("stats").textContent = `${stats.documents.toLocaleString()} documents · ${stats.context_rows.toLocaleString()} context rows`;
  optionList($("type"), stats.document_types, "All types");
  optionList($("status"), stats.statuses, "All statuses");
  optionList($("authority"), stats.authorities, "All authorities");
  await search();
}

function buildQuery() {
  const params = new URLSearchParams();
  for (const id of ["q", "type", "status", "authority"]) {
    const value = $(id).value.trim();
    if (value) params.set(id, value);
  }
  params.set("limit", "100");
  return params;
}

async function search() {
  const data = await fetch(`/api/documents?${buildQuery()}`).then((r) => r.json());
  state.documents = data.documents;
  $("result-count").textContent = `${data.total.toLocaleString()} document${data.total === 1 ? "" : "s"}`;
  renderList();
  const activeStillVisible = data.documents.some((doc) => doc.document_id === state.activeId);
  if ((!state.activeId || !activeStillVisible) && data.documents.length) {
    await openDocument(data.documents[0].document_id);
  } else if (!data.documents.length) {
    state.activeId = null;
    $("workspace").innerHTML = `<div class="empty">No matching documents.</div>`;
  }
}

function renderList() {
  $("documents").innerHTML = state.documents.map((doc) => `
    <button class="doc-card ${doc.document_id === state.activeId ? "active" : ""}" onclick="openDocument(${doc.document_id})">
      <div class="doc-title">${escapeHtml(doc.title)}</div>
      <div class="doc-fields">
        <span class="pill">${compact(doc.document_number)}</span>
        <span class="pill">${compact(doc.document_type)}</span>
        <span class="pill">${compact(doc.issuing_authority)}</span>
        <span class="pill doc-date">${compact(doc.effective_date)}</span>
        <span class="pill">${compact(doc.validity_status)}</span>
      </div>
    </button>
  `).join("") || `<div class="empty" style="min-height:220px">No matching documents.</div>`;
}

async function openDocument(documentId) {
  state.activeId = documentId;
  renderList();
  $("workspace").innerHTML = `<div class="empty">Loading document...</div>`;
  const doc = await fetch(`/api/document/${documentId}`).then((r) => r.json());
  renderDocument(doc);
}

function renderDocument(doc) {
  const m = doc.metadata;
  const sections = doc.sections || [];
  const banner = doc.pdf_review
    ? `<div class="banner">PDF review item: ${compact(doc.pdf_review.review_reason)}</div>`
    : "";
  $("workspace").innerHTML = `
    <section class="doc-top">
      <div class="doc-heading">
        <div>
          <h2>${escapeHtml(m.title)}</h2>
          <div class="stats">${compact(m.document_number)} · ${compact(m.document_type)} · ${compact(m.issuing_authority)}</div>
        </div>
        <div class="actions">
          ${m.source_url ? `<a class="source-link" href="${escapeHtml(m.source_url)}" target="_blank" rel="noreferrer">Open source</a>` : ""}
        </div>
      </div>
      <div class="meta-grid">
        ${meta("Issued", m.issued_date)}
        ${meta("Effective", m.effective_date)}
        ${meta("Expired", m.expired_date)}
        ${meta("Status", m.validity_status)}
        ${meta("Document ID", m.document_id)}
      </div>
      ${banner}
    </section>
    <section class="doc-body">
      <aside class="outline">
        <div class="outline-title">
          <strong>Structured Sections</strong>
          <span class="stats">${sections.length.toLocaleString()}</span>
        </div>
        <div class="hint">Article, clause, point, table, form, and annex rows from the export.</div>
        <div class="section-list">${renderSections(sections)}</div>
      </aside>
      <section class="preview">
        <iframe id="document-frame" sandbox="" title="Document preview"></iframe>
      </section>
    </section>
  `;
  $("document-frame").srcdoc = doc.document_html;
}

function meta(label, value) {
  return `<div class="meta-item"><div class="label">${label}</div><div class="value">${compact(value)}</div></div>`;
}

function renderSections(sections) {
  return sections.slice(0, 350).map((section) => {
    const anchor = section.stable_anchor || section.context_type || "section";
    const heading = section.heading && section.heading !== section.content_text ? `<strong>${escapeHtml(section.heading)}</strong><br>` : "";
    return `<article class="section-card">
      <div class="section-type">${escapeHtml(section.context_type || "section")}</div>
      <div class="section-anchor">${escapeHtml(anchor)}</div>
      <div class="section-text">${heading}${escapeHtml(section.content_text || "").slice(0, 420)}</div>
    </article>`;
  }).join("") || `<div class="stats">No structured sections available.</div>`;
}

for (const id of ["type", "status", "authority"]) {
  $(id).addEventListener("change", search);
}
$("q").addEventListener("input", () => {
  clearTimeout(state.searchTimer);
  state.searchTimer = setTimeout(search, 180);
});
$("clear").addEventListener("click", () => {
  for (const id of ["q", "type", "status", "authority"]) $(id).value = "";
  state.activeId = null;
  search();
});

boot().catch((error) => {
  console.error(error);
  $("workspace").innerHTML = `<div class="empty">Failed to load dataset preview.</div>`;
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
