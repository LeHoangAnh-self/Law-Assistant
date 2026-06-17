from datetime import date
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from rag_service.models import SourceReference


class QdrantVectorStore:
    def __init__(self, url: str, collection_name: str, vector_size: int) -> None:
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name
        self.vector_size = vector_size
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
        self.client.upsert(collection_name=self.collection_name, points=points, wait=True)
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
        hits = self.client.search(
            collection_name=self.collection_name,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            SourceReference(
                document_id=int(hit.payload["document_id"]),
                chunk_id=str(hit.payload["chunk_id"]),
                title=hit.payload.get("title"),
                document_number=hit.payload.get("document_number"),
                source=hit.payload.get("source"),
                issued_date=hit.payload.get("issued_date"),
                score=float(hit.score),
                text=hit.payload.get("text", ""),
            )
            for hit in hits
        ]

    @staticmethod
    def _build_filter(
        filters: dict[str, str],
        issued_date_lte: date | None = None,
    ) -> qmodels.Filter | None:
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
