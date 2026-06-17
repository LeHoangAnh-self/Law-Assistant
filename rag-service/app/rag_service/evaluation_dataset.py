import argparse
from pathlib import Path

from rag_service.baochinhphu_dataset import run_scrapy


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the standard RAG evaluation set from Bảo Chính Phủ citizen answers."
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--output", default="evaluation/rag_test_set.json")
    parser.add_argument("--delay-seconds", type=float, default=0.5)
    args = parser.parse_args()

    run_scrapy(
        output_path=Path(args.output),
        limit=args.limit,
        max_pages=args.max_pages,
        delay_seconds=args.delay_seconds,
    )
    print(f"Wrote up to {args.limit} cases to {args.output}")


if __name__ == "__main__":
    main()
