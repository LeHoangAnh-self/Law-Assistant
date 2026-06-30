#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from rag_service.config import get_settings  # noqa: E402
from rag_service.index_audit import (  # noqa: E402
    fetch_law_service_document_ids,
    fetch_qdrant_indexed_document_ids,
    find_missing_ids,
)
from rag_service.worker import index_document  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Requeue Law Service documents that are missing from Qdrant."
    )
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--scroll-limit", type=int, default=2000)
    parser.add_argument("--limit", type=int, default=0, help="Only requeue the first N missing IDs.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    source_ids = fetch_law_service_document_ids(str(settings.law_service_base_url), args.page_size)
    indexed_ids = fetch_qdrant_indexed_document_ids(
        str(settings.qdrant_url),
        settings.qdrant_collection,
        args.scroll_limit,
    )
    missing_ids = find_missing_ids(source_ids, indexed_ids)
    if args.limit > 0:
        missing_ids = missing_ids[: args.limit]

    print(f"Law Service documents: {len(source_ids)}")
    print(f"Qdrant indexed documents: {len(indexed_ids)}")
    print(f"Documents to requeue: {len(missing_ids)}")
    if missing_ids:
        print(f"Sample: {missing_ids[:20]}")

    if args.dry_run:
        return

    for document_id in missing_ids:
        index_document.delay(document_id)
    print(f"Queued {len(missing_ids)} indexing tasks.")


if __name__ == "__main__":
    main()
