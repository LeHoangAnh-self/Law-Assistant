from datetime import date
from typing import TypeVar
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from rag_service.filters import validate_filter_keys
from rag_service.models import SourceReference

T = TypeVar("T")


class QdrantVectorStore:
    def __init__(
        self,
        url: str,
        collection_name: str,
        vector_size: int,
        timeout: float = 120.0,
        upsert_batch_size: int = 64,
    ) -> None:
        self.client = QdrantClient(url=url, timeout=timeout)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.upsert_batch_size = upsert_batch_size
        self._collection_ready = False

    def ensure_collection(self) -> None:
        if self._collection_ready:
            return
        collections = self.client.get_collections().collections
        if any(collection.name == self.collection_name for collection in collections):
            self._collection_ready = True
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.vector_size,
                distance=qmodels.Distance.COSINE,
            ),
        )
        self._collection_ready = True

    def replace_document_chunks(
        self,
        document_id: int,
        chunks: list[dict],
        vectors: list[list[float]],
        delete_existing: bool = False,
    ) -> int:
        self.ensure_collection()
        if delete_existing:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=qmodels.FilterSelector(
                    filter=qmodels.Filter(
                        must=[
                            qmodels.FieldCondition(
                                key="document_id",
                                match=qmodels.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        if not chunks:
            return 0

        points = [
            qmodels.PointStruct(
                id=str(uuid5(NAMESPACE_URL, chunk["chunk_id"])),
                vector=vector,
                payload=chunk,
            )
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
        for point_batch in self._batched(points, self.upsert_batch_size):
            self.client.upsert(collection_name=self.collection_name, points=point_batch, wait=True)
        return len(points)

    def search(
        self,
        vector: list[float],
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        self.ensure_collection()
        query_filter = self._build_filter(filters or {}, issued_date_lte=issued_date_lte)
        if hasattr(self.client, "search"):
            hits = self.client.search(
                collection_name=self.collection_name,
                query_vector=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
        else:
            hits = self.client.query_points(
                collection_name=self.collection_name,
                query=vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            ).points
        return [
            SourceReference(
                document_id=int(hit.payload["document_id"]),
                chunk_id=str(hit.payload["chunk_id"]),
                title=hit.payload.get("title"),
                document_number=hit.payload.get("document_number"),
                document_type=hit.payload.get("document_type"),
                validity_status=hit.payload.get("validity_status"),
                source=hit.payload.get("source"),
                source_url=hit.payload.get("source_url"),
                external_source=hit.payload.get("external_source"),
                external_docid=hit.payload.get("external_docid"),
                issued_date=hit.payload.get("issued_date"),
                effective_date=hit.payload.get("effective_date"),
                expired_date=hit.payload.get("expired_date"),
                issuing_authority=hit.payload.get("issuing_authority"),
                scope=hit.payload.get("scope"),
                legal_path=hit.payload.get("legal_path"),
                chunk_level=hit.payload.get("chunk_level"),
                parent_id=hit.payload.get("parent_id"),
                parent_article_number=hit.payload.get("parent_article_number"),
                article_number=hit.payload.get("article_number"),
                clause_number=hit.payload.get("clause_number"),
                point_number=hit.payload.get("point_number"),
                chunking_strategy=hit.payload.get("chunking_strategy"),
                score=float(hit.score),
                text=self._hydrated_text(hit.payload),
                retrieval_text=hit.payload.get("retrieval_text"),
                child_text=hit.payload.get("child_text"),
                parent_text=hit.payload.get("parent_text"),
            )
            for hit in hits
        ]

    def search_payload_text(
        self,
        terms: list[str],
        limit: int,
        issued_date_lte: date | None = None,
        max_scan: int = 50000,
        document_numbers: list[str] | None = None,
    ) -> list[SourceReference]:
        self.ensure_collection()
        candidates: list[SourceReference] = []
        if document_numbers:
            per_document_limit = max_scan
            for document_number in document_numbers:
                candidates.extend(
                    self._scroll_payloads(
                        limit=per_document_limit,
                        issued_date_lte=issued_date_lte,
                        filters={"document_number": document_number},
                    )
                )
        else:
            candidates = self._scroll_payloads(limit=max_scan, issued_date_lte=issued_date_lte)
        scored: list[tuple[int, SourceReference]] = []
        lowered_terms = [term.lower() for term in terms]
        for reference in candidates:
            metadata_haystack = " ".join(
                value or ""
                for value in [reference.title, reference.document_number, reference.legal_path]
            ).lower()
            text_haystack = (reference.text or "").lower()
            score = sum(1 for term in lowered_terms if term in metadata_haystack)
            score += sum(3 for term in lowered_terms if term in text_haystack)
            if score:
                scored.append((score, reference.model_copy(update={"score": float(score)})))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [reference for _, reference in scored[:limit]]

    def get_document_chunks(
        self,
        document_id: int,
        issued_date_lte: date | None = None,
        limit: int = 5000,
    ) -> list[SourceReference]:
        self.ensure_collection()
        return sorted(
            self._scroll_payloads(
                limit=limit,
                issued_date_lte=issued_date_lte,
                filters={"document_id": document_id},
            ),
            key=self._chunk_sort_key,
        )

    def get_chunks_by_document_number(
        self,
        document_number: str,
        issued_date_lte: date | None = None,
        limit: int = 5000,
    ) -> list[SourceReference]:
        self.ensure_collection()
        return sorted(
            self._scroll_payloads(
                limit=limit,
                issued_date_lte=issued_date_lte,
                filters={"document_number": document_number},
            ),
            key=self._chunk_sort_key,
        )

    def scroll_references(
        self,
        limit: int,
        issued_date_lte: date | None = None,
        filters: dict[str, object] | None = None,
    ) -> list[SourceReference]:
        self.ensure_collection()
        return self._scroll_payloads(
            limit=limit,
            issued_date_lte=issued_date_lte,
            filters=filters,
        )

    @classmethod
    def get_adjacent_chunks(
        cls,
        chunks: list[SourceReference],
        chunk_id: str,
        window: int = 1,
    ) -> list[SourceReference]:
        chunk_index = next(
            (index for index, chunk in enumerate(chunks) if chunk.chunk_id == chunk_id),
            None,
        )
        if chunk_index is None:
            return []
        start = max(0, chunk_index - window)
        end = min(len(chunks), chunk_index + window + 1)
        return [chunk for chunk in chunks[start:end] if chunk.chunk_id != chunk_id]

    @staticmethod
    def _chunk_sort_key(reference: SourceReference) -> tuple[int, str]:
        suffix = reference.chunk_id.rsplit(":", 1)[-1]
        try:
            return (int(suffix), reference.chunk_id)
        except ValueError:
            return (10**9, reference.chunk_id)

    def _scroll_payloads(
        self,
        limit: int,
        issued_date_lte: date | None = None,
        filters: dict[str, object] | None = None,
    ) -> list[SourceReference]:
        query_filter = self._build_filter(filters or {}, issued_date_lte=issued_date_lte)
        all_records = []
        offset = None
        remaining = limit
        while remaining > 0:
            records, offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=min(256, remaining),
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            all_records.extend(records)
            remaining -= len(records)
            if not offset or not records:
                break
        return [
            SourceReference(
                document_id=int(record.payload["document_id"]),
                chunk_id=str(record.payload["chunk_id"]),
                title=record.payload.get("title"),
                document_number=record.payload.get("document_number"),
                document_type=record.payload.get("document_type"),
                validity_status=record.payload.get("validity_status"),
                source=record.payload.get("source"),
                source_url=record.payload.get("source_url"),
                external_source=record.payload.get("external_source"),
                external_docid=record.payload.get("external_docid"),
                issued_date=record.payload.get("issued_date"),
                effective_date=record.payload.get("effective_date"),
                expired_date=record.payload.get("expired_date"),
                issuing_authority=record.payload.get("issuing_authority"),
                scope=record.payload.get("scope"),
                legal_path=record.payload.get("legal_path"),
                chunk_level=record.payload.get("chunk_level"),
                parent_id=record.payload.get("parent_id"),
                parent_article_number=record.payload.get("parent_article_number"),
                article_number=record.payload.get("article_number"),
                clause_number=record.payload.get("clause_number"),
                point_number=record.payload.get("point_number"),
                chunking_strategy=record.payload.get("chunking_strategy"),
                score=0.0,
                text=self._hydrated_text(record.payload),
                retrieval_text=record.payload.get("retrieval_text"),
                child_text=record.payload.get("child_text"),
                parent_text=record.payload.get("parent_text"),
            )
            for record in all_records
        ]

    @staticmethod
    def _hydrated_text(payload: dict) -> str:
        if payload.get("chunk_level") == "child" and payload.get("parent_text"):
            return payload["parent_text"]
        return payload.get("text", "")

    @staticmethod
    def _build_filter(
        filters: dict[str, object],
        issued_date_lte: date | None = None,
    ) -> qmodels.Filter | None:
        filters = validate_filter_keys(filters)
        conditions = [
            qmodels.FieldCondition(key=key, match=qmodels.MatchValue(value=value))
            for key, value in filters.items()
            if value
        ]
        if issued_date_lte:
            conditions.append(
                qmodels.FieldCondition(
                    key="issued_date",
                    range=qmodels.DatetimeRange(lte=issued_date_lte),
                )
            )
        if not conditions:
            return None
        return qmodels.Filter(must=conditions)

    @staticmethod
    def _batched(items: list[T], batch_size: int) -> list[list[T]]:
        return [items[index : index + batch_size] for index in range(0, len(items), batch_size)]
