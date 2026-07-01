from datetime import date

from rag_service.bm25_retriever import BM25Retriever
from rag_service.hybrid_retriever import HybridRetriever
from rag_service.models import SourceReference
from rag_service.retrieval import DenseRetriever, RetrievalQuery


def reference(
    chunk_id: str,
    *,
    title: str,
    document_number: str,
    text: str,
    article_number: str | None = None,
    clause_number: str | None = None,
    point_number: str | None = None,
    legal_path: str | None = None,
) -> SourceReference:
    document_id = int(chunk_id.split(":", 1)[0])
    return SourceReference(
        document_id=document_id,
        chunk_id=chunk_id,
        title=title,
        document_number=document_number,
        article_number=article_number,
        clause_number=clause_number,
        point_number=point_number,
        legal_path=legal_path,
        score=0,
        text=text,
        retrieval_text=f"{title}\nSố/Ký hiệu: {document_number}\n{legal_path or ''}\n{text}",
    )


LABOR_127 = reference(
    "139264:127",
    title="Bộ luật Lao động số 45/2019/QH14",
    document_number="45/2019/QH14",
    article_number="127",
    legal_path="Chương VIII > Điều 127. Các hành vi bị nghiêm cấm khi xử lý kỷ luật lao động",
    text=(
        "Điều 127. Cấm xâm phạm sức khỏe, danh dự, tính mạng, uy tín, nhân phẩm "
        "của người lao động; cấm dùng hình thức phạt tiền, cắt lương thay việc "
        "xử lý kỷ luật lao động."
    ),
)
LABOR_35 = reference(
    "139264:35",
    title="Bộ luật Lao động số 45/2019/QH14",
    document_number="45/2019/QH14",
    article_number="35",
    legal_path="Chương III > Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động",
    text="Điều 35. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động.",
)
ENTERPRISE = reference(
    "900:12",
    title="Luật Doanh nghiệp số 59/2020/QH14",
    document_number="59/2020/QH14",
    article_number="12",
    legal_path="Điều 12. Người đại diện theo pháp luật",
    text="Doanh nghiệp phải có người đại diện theo pháp luật.",
)
PAYROLL_PENALTY = reference(
    "777:3",
    title="Nghị định xử phạt vi phạm hành chính về lao động",
    document_number="12/2022/NĐ-CP",
    article_number="17",
    text="Quy định xử phạt khi người sử dụng lao động trả lương không đúng hạn.",
)


class MemoryVectorStore:
    def __init__(self, references: list[SourceReference]) -> None:
        self.references = references

    def scroll_references(
        self,
        limit: int,
        issued_date_lte: date | None = None,
        filters: dict[str, object] | None = None,
    ) -> list[SourceReference]:
        _ = issued_date_lte
        filters = filters or {}
        matches = self.references
        for key, value in filters.items():
            matches = [reference for reference in matches if getattr(reference, key) == value]
        return matches[:limit]


class FakeDenseRetriever(DenseRetriever):
    def __init__(self, hits: list[tuple[SourceReference, float]] | None = None) -> None:
        self.hits = hits or []

    def retrieve(
        self,
        query: RetrievalQuery,
        limit: int,
        filters: dict[str, str] | None = None,
        issued_date_lte: date | None = None,
    ) -> list[SourceReference]:
        _ = (query, filters, issued_date_lte)
        return [
            reference.model_copy(update={"score": score, "dense_score": score})
            for reference, score in self.hits[:limit]
        ]


def hybrid(
    references: list[SourceReference],
    dense_hits: list[tuple[SourceReference, float]] | None = None,
) -> HybridRetriever:
    return HybridRetriever(
        dense_retriever=FakeDenseRetriever(dense_hits),
        lexical_retriever=BM25Retriever(MemoryVectorStore(references)),
        dense_limit=50,
        lexical_limit=50,
    )


def test_hybrid_retriever_prioritizes_exact_document_number_query() -> None:
    retriever = hybrid([LABOR_127, LABOR_35, ENTERPRISE])

    results = retriever.retrieve(RetrievalQuery(text="45/2019/QH14 Điều 127 phạt tiền"), limit=5)

    assert results[0].chunk_id == "139264:127"
    assert results[0].bm25_score is not None
    assert results[0].exact_match_boost >= 5.5
    assert results[0].hybrid_score == results[0].score


def test_hybrid_retriever_prioritizes_exact_article_query() -> None:
    retriever = hybrid([LABOR_127, LABOR_35, PAYROLL_PENALTY])

    results = retriever.retrieve(RetrievalQuery(text="Điều 127 Bộ luật Lao động"), limit=5)

    assert results[0].chunk_id == "139264:127"
    assert results[0].article_number == "127"
    assert results[0].exact_match_boost >= 2.5


def test_hybrid_retriever_keeps_semantic_paraphrase_dense_candidate() -> None:
    retriever = hybrid(
        [ENTERPRISE, PAYROLL_PENALTY],
        dense_hits=[(LABOR_127, 0.92), (ENTERPRISE, 0.4)],
    )

    results = retriever.retrieve(
        RetrievalQuery(text="công ty trừ thẳng tiền lương để kỷ luật nhân viên"),
        limit=5,
    )

    assert results[0].chunk_id == "139264:127"
    assert results[0].dense_score == 0.92
    assert results[0].bm25_score is None


def test_hybrid_retriever_handles_informal_query_plus_legal_reference() -> None:
    retriever = hybrid(
        [LABOR_127, LABOR_35, PAYROLL_PENALTY],
        dense_hits=[(PAYROLL_PENALTY, 0.95), (LABOR_127, 0.7)],
    )

    results = retriever.retrieve(
        RetrievalQuery(
            text="Điều 127 Bộ luật Lao động có cho công ty phạt tiền nhân viên không?"
        ),
        limit=5,
    )

    assert results[0].chunk_id == "139264:127"
    assert results[0].dense_score == 0.7
    assert results[0].bm25_score is not None
    assert results[0].exact_match_boost >= 2.5
