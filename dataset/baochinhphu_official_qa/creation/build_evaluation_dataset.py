import argparse
from pathlib import Path

from baochinhphu_dataset import DEFAULT_LAW_DB_PATH, DEFAULT_OUTPUT, LegalDocumentIndex, run_scrapy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the standard RAG evaluation set from Bảo Chính Phủ citizen answers."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    parser.add_argument("--law-db-path", default=DEFAULT_LAW_DB_PATH)
    parser.add_argument(
        "--related-depth",
        type=int,
        default=1,
        help="Depth for discovering additional candidates from related-article links.",
    )
    parser.add_argument(
        "--oldest-first",
        action="store_true",
        help="Scan listing pages from older to newer instead of the default newer-to-older order.",
    )
    parser.add_argument(
        "--require-all-linked-documents",
        action="store_true",
        help="Only keep pages when every direct legal-document link matches the local DB.",
    )
    args = parser.parse_args()
    legal_document_index = LegalDocumentIndex.from_parquet(Path(args.law_db_path))

    run_scrapy(
        output_path=Path(args.output),
        limit=args.limit,
        max_pages=args.max_pages,
        delay_seconds=args.delay_seconds,
        legal_document_index=legal_document_index,
        require_all_linked_documents=args.require_all_linked_documents,
        newest_first=not args.oldest_first,
        related_depth=args.related_depth,
    )
    print(f"Wrote up to {args.limit} cases to {args.output}")


if __name__ == "__main__":
    main()
