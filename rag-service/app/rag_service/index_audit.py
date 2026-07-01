import argparse
from collections.abc import Iterable

import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from rag_service.config import get_settings


def find_missing_ids(source_ids: Iterable[int], indexed_ids: Iterable[int]) -> list[int]:
    return sorted(set(source_ids) - set(indexed_ids))


def fetch_law_service_document_ids(base_url: str, page_size: int) -> set[int]:
    base_url = base_url.rstrip("/")
    with httpx.Client(timeout=60.0) as client:
        response = client.get(f"{base_url}/api/documents/ids")
        if response.status_code == 200:
            ids = {int(document_id) for document_id in response.json()}
            print(f"Fetched Law Service IDs from /api/documents/ids: {len(ids)}", flush=True)
            return ids
        if response.status_code != 404:
            response.raise_for_status()

    document_ids: set[int] = set()
    page = 0
    total_pages = 1
    with httpx.Client(timeout=60.0) as client:
        while page < total_pages:
            response = client.get(
                f"{base_url}/api/documents",
                params={"page": page, "size": page_size},
            )
            response.raise_for_status()
            payload = response.json()
            document_ids.update(int(document["id"]) for document in payload["content"])
            total_pages = int(payload.get("totalPages", total_pages))
            page += 1
            if page % 100 == 0 or page == total_pages:
                print(f"Fetched Law Service IDs: page {page}/{total_pages}", flush=True)
    return document_ids


def fetch_qdrant_indexed_document_ids(
    qdrant_url: str,
    collection_name: str,
    scroll_limit: int,
    client: QdrantClient | None = None,
) -> set[int]:
    client = client or QdrantClient(url=qdrant_url)
    indexed_ids: set[int] = set()
    offset = None
    scanned_points = 0
    while True:
        try:
            points, offset = client.scroll(
                collection_name=collection_name,
                limit=scroll_limit,
                offset=offset,
                with_payload=["document_id"],
                with_vectors=False,
            )
        except UnexpectedResponse as exc:
            if exc.status_code == 404 and b"Collection" in exc.content:
                print(
                    f"Qdrant collection '{collection_name}' does not exist yet; "
                    "treating indexed count as 0.",
                    flush=True,
                )
                return set()
            raise
        scanned_points += len(points)
        for point in points:
            if point.payload and point.payload.get("document_id") is not None:
                indexed_ids.add(int(point.payload["document_id"]))
        if scanned_points and scanned_points % 50000 == 0:
            print(f"Scanned Qdrant points: {scanned_points}", flush=True)
        if offset is None:
            break
    print(f"Scanned Qdrant points: {scanned_points}", flush=True)
    return indexed_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Law Service document IDs against Qdrant indexed IDs."
    )
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--scroll-limit", type=int, default=1000)
    parser.add_argument("--sample-size", type=int, default=50)
    args = parser.parse_args()

    settings = get_settings()
    source_ids = fetch_law_service_document_ids(str(settings.law_service_base_url), args.page_size)
    indexed_ids = fetch_qdrant_indexed_document_ids(
        str(settings.qdrant_url),
        settings.qdrant_collection,
        args.scroll_limit,
    )
    missing_ids = find_missing_ids(source_ids, indexed_ids)
    extra_ids = sorted(indexed_ids - source_ids)

    print("")
    print(f"Law Service documents: {len(source_ids)}")
    print(f"Qdrant indexed documents: {len(indexed_ids)}")
    print(f"Missing documents: {len(missing_ids)}")
    print(f"Extra indexed IDs not in Law Service: {len(extra_ids)}")
    if missing_ids:
        print(f"Missing sample: {missing_ids[: args.sample_size]}")
        print("")
        print("To requeue the first missing document manually:")
        print(
            'curl -H "X-Admin-Token: $LAW_ADMIN_TOKEN" '
            f'-X POST "http://localhost:8080/api/documents/{missing_ids[0]}/embedding-events"'
        )


if __name__ == "__main__":
    main()
