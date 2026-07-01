import asyncio
from datetime import date

from rag_service.config import Settings
from rag_service.models import AskRequest, SourceReference
from rag_service.pipeline import RagPipeline


class FakeEmbeddingModel:
    def __init__(self) -> None:
        self.seen_text: str | None = None
        self.seen_texts: list[str] = []

    def embed_one(self, text: str) -> list[float]:
        self.seen_text = text
        self.seen_texts.append(text)
        return [0.1, 0.2]


class FakeVectorStore:
    def __init__(self) -> None:
        self.issued_date_lte = None
        self.last_limit = None
        self.payload_terms = None
        self.payload_terms_seen = []
        self.payload_document_numbers = []
        self.document_chunks_by_id: dict[int, list[SourceReference]] = {}
        self.document_chunks_by_number: dict[str, list[SourceReference]] = {}

    def search(
        self,
        _vector: list[float],
        limit: int,
        filters: dict[str, str],
        issued_date_lte=None,
    ):
        assert filters == {}
        self.last_limit = limit
        self.issued_date_lte = issued_date_lte
        return []

    def search_payload_text(
        self,
        terms: list[str],
        limit: int,
        issued_date_lte=None,
        document_numbers: list[str] | None = None,
    ):
        _ = (limit, issued_date_lte)
        self.payload_terms = terms
        self.payload_terms_seen.extend(terms)
        if document_numbers:
            self.payload_document_numbers.extend(document_numbers)
        return []

    def get_document_chunks(self, document_id: int, issued_date_lte=None, limit: int = 5000):
        self.issued_date_lte = issued_date_lte
        return self.document_chunks_by_id.get(document_id, [])[:limit]

    def get_chunks_by_document_number(self, document_number: str, issued_date_lte=None, limit: int = 5000):
        self.issued_date_lte = issued_date_lte
        return self.document_chunks_by_number.get(document_number, [])[:limit]

    @staticmethod
    def get_adjacent_chunks(chunks: list[SourceReference], chunk_id: str, window: int = 1):
        return [
            chunk
            for index, chunk in enumerate(chunks)
            if chunk.chunk_id != chunk_id
            and abs(index - next(i for i, item in enumerate(chunks) if item.chunk_id == chunk_id)) <= window
        ]


class FakeReranker:
    def rerank(self, _query: str, references: list, limit: int):
        assert limit == 5
        return references


class FakeLlmClient:
    def __init__(self, answers: list[str] | None = None) -> None:
        self.answers = answers or ["answer"]
        self.prompts: list[str] = []

    async def generate(self, _prompt: str) -> str:
        self.prompts.append(_prompt)
        if len(self.prompts) <= len(self.answers):
            return self.answers[len(self.prompts) - 1]
        return self.answers[-1]


def labor_article_35() -> SourceReference:
    return SourceReference(
        document_id=139264,
        chunk_id="139264:25",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        article_number="35",
        legal_path="Chương III > Điều 35. Quyền đơn phương chấm dứt hợp đồng lao động",
        validity_status="Còn hiệu lực",
        score=10,
        text=(
            "Điều 35. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động "
            "không cần báo trước nếu không được trả đủ lương hoặc trả lương không đúng thời hạn."
        ),
    )


def test_pipeline_prefixes_query_with_embedding_instruction() -> None:
    embedding_model = FakeEmbeddingModel()
    settings = Settings(
        embedding_query_instruction="Instruct: test\nQuery: ",
        embedding_dimension=2,
    )
    pipeline = RagPipeline(
        settings,
        embedding_model=embedding_model,
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="  Văn bản nào còn hiệu lực?  ", top_k=5))
    )

    assert embedding_model.seen_text == "Instruct: test\nQuery: Văn bản nào còn hiệu lực?"
    assert response.answer == "answer"


def test_pipeline_returns_retrieval_diagnostics_for_selected_sources() -> None:
    labor_article = SourceReference(
        document_id=139264,
        chunk_id="139264:25",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        validity_status="Còn hiệu lực",
        effective_date="2021-01-01",
        score=10,
        text="Điều 35. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động.",
    )

    class DiagnosticVectorStore(FakeVectorStore):
        def search(self, _vector, limit, filters, issued_date_lte=None):
            _ = (limit, filters, issued_date_lte)
            return [labor_article]

    pipeline = RagPipeline(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=DiagnosticVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="Tôi muốn nghỉ việc theo Điều 35 thì sao?", top_k=5))
    )

    assert response.retrieval_diagnostics
    assert response.retrieval_diagnostics["authoritative_source_count"] >= 1
    assert "Đánh giá chất lượng nguồn" in pipeline.llm_client.prompts[0]


def test_pipeline_passes_retrieval_cutoff_to_vector_store() -> None:
    vector_store = FakeVectorStore()
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=FakeEmbeddingModel(),
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    asyncio.run(
        pipeline.ask(
            AskRequest(
                question="Quy định nào áp dụng?",
                top_k=5,
                retrieval_cutoff_date="2025-03-06",
            )
        )
    )

    assert vector_store.issued_date_lte.isoformat() == "2025-03-06"


def test_pipeline_retrieves_with_current_question_not_conversation_context() -> None:
    embedding_model = FakeEmbeddingModel()
    pipeline = RagPipeline(
        Settings(
            embedding_query_instruction="Instruct: test\nQuery: ",
            embedding_dimension=2,
        ),
        embedding_model=embedding_model,
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    asyncio.run(
        pipeline.ask(
            AskRequest(
                question="bán bất động sản 2 tỷ thì thuế TNCN ra sao?",
                top_k=5,
                conversation_context="Trợ lý: câu trả lời dài cũ về tiền lương và biểu lũy tiến",
            )
        )
    )

    all_queries = "\n".join(embedding_model.seen_texts)
    assert "câu trả lời dài cũ" not in all_queries
    assert "bán bất động sản 2 tỷ" in all_queries
    assert "chuyển nhượng bất động sản" in all_queries


def test_pipeline_expands_exemption_and_co_owner_tax_queries() -> None:
    embedding_model = FakeEmbeddingModel()
    pipeline = RagPipeline(
        Settings(
            embedding_query_instruction="Instruct: test\nQuery: ",
            embedding_dimension=2,
        ),
        embedding_model=embedding_model,
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question=(
                    "Hôm nay là 30/06/2026. Vợ chồng đứng tên chung căn hộ, "
                    "vợ có đất riêng. Có được miễn thuế TNCN nhà ở duy nhất không?"
                ),
                top_k=5,
            )
        )
    )

    all_queries = "\n".join(embedding_model.seen_texts)
    assert "nhà ở duy nhất" in all_queries
    assert "đồng sở hữu vợ chồng" in all_queries
    assert "Thông tư 111/2013/TT-BTC" in all_queries
    assert "Điều 12 đồng sở hữu nghĩa vụ thuế tỷ lệ bình quân" in all_queries
    assert response.retrieval_query


def test_pipeline_requests_must_have_sources_for_only_home_exemption() -> None:
    vector_store = FakeVectorStore()
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=FakeEmbeddingModel(),
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    asyncio.run(
        pipeline.ask(
            AskRequest(
                question="Vợ chồng đồng sở hữu căn hộ, miễn thuế TNCN nhà ở duy nhất thế nào?",
                top_k=5,
            )
        )
    )

    assert vector_store.payload_terms
    assert "111/2013/TT-BTC" in vector_store.payload_terms_seen or "111/2013/TT-BTC" in vector_store.payload_document_numbers
    assert "tỷ lệ bình quân" in vector_store.payload_terms_seen
    assert "Điều 12" in vector_store.payload_terms_seen
    assert "111/2013/TT-BTC" in vector_store.payload_document_numbers


def test_pipeline_expands_article_3_hit_to_circular_111_article_12() -> None:
    article_3 = SourceReference(
        document_id=37590,
        chunk_id="37590:28",
        title="Thông tư 111/2013/TT-BTC",
        document_number="111/2013/TT-BTC",
        validity_status="Hết hiệu lực một phần",
        score=20,
        text=(
            "Điều 3. Miễn thuế. Nhà ở duy nhất, đất ở duy nhất. "
            "Chồng hoặc vợ có nhà ở, đất ở riêng không được miễn thuế. 183 ngày."
        ),
    )
    article_12 = SourceReference(
        document_id=37590,
        chunk_id="37590:90",
        title="Thông tư 111/2013/TT-BTC",
        document_number="111/2013/TT-BTC",
        validity_status="Hết hiệu lực một phần",
        score=2,
        text=(
            "Điều 12. Trường hợp bất động sản thuộc sở hữu chung thì nghĩa vụ thuế "
            "được xác định riêng cho từng người theo tỷ lệ sở hữu; nếu không có tài liệu "
            "hợp pháp thì xác định theo tỷ lệ bình quân."
        ),
    )

    class Article3VectorStore(FakeVectorStore):
        def search(self, _vector, limit, filters, issued_date_lte=None):
            _ = (limit, filters, issued_date_lte)
            return [article_3]

        def search_payload_text(self, terms, limit, issued_date_lte=None, document_numbers=None):
            super().search_payload_text(terms, limit, issued_date_lte, document_numbers)
            return []

    vector_store = Article3VectorStore()
    vector_store.document_chunks_by_id[37590] = [article_3, article_12]
    pipeline = RagPipeline(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question=(
                    "Vợ chồng đồng sở hữu căn hộ, hỏi miễn thuế TNCN nhà ở duy nhất "
                    "và nếu một người không đủ điều kiện thì phân bổ thuế thế nào?"
                ),
                top_k=5,
            )
        )
    )

    assert "37590:28" in [reference.chunk_id for reference in response.references]
    assert "37590:90" in [reference.chunk_id for reference in response.references]


def test_pipeline_labor_issue_queries_required_labor_code_articles() -> None:
    embedding_model = FakeEmbeddingModel()
    vector_store = FakeVectorStore()
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=embedding_model,
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question=(
                    "Tôi nghỉ việc ngay không báo trước vì công ty trả lương trễ hơn 20 ngày, "
                    "đổi địa điểm làm việc khác hợp đồng, giữ lương tháng cuối và không chốt BHXH. "
                    "Công ty đòi bồi thường nửa tháng lương."
                ),
                top_k=5,
            )
        )
    )

    all_queries = "\n".join(embedding_model.seen_texts)
    assert response.classification == "labor.resignation"
    assert "Điều 35 Bộ luật Lao động 2019" in all_queries
    assert "Điều 40 Bộ luật Lao động 2019" in all_queries
    assert "Điều 48 Bộ luật Lao động 2019" in all_queries
    assert "Điều 97 Bộ luật Lao động 2019" in all_queries
    assert "45/2019/QH14" in vector_store.payload_document_numbers
    assert "không cần báo trước" in vector_store.payload_terms_seen
    assert "xác nhận thời gian đóng bảo hiểm xã hội" in vector_store.payload_terms_seen


def test_pipeline_labor_resignation_pins_required_articles_for_deployment_wording() -> None:
    embedding_model = FakeEmbeddingModel()
    vector_store = FakeVectorStore()
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=embedding_model,
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question=(
                    "Tôi ký hợp đồng lao động không xác định thời hạn, địa điểm làm việc trong hợp đồng là TP.HCM. "
                    "Công ty yêu cầu tôi sang Bình Dương làm việc nhưng tôi không đồng ý bằng văn bản. "
                    "Lương bị trả muộn hơn 20 ngày trong 2 tháng liên tiếp nên tôi gửi email nghỉ việc ngay. "
                    "HR nói tôi nghỉ trái pháp luật, đòi giữ lương cuối và không chốt BHXH."
                ),
                top_k=5,
            )
        )
    )

    all_queries = "\n".join(embedding_model.seen_texts)
    assert response.classification == "labor.resignation"
    assert "Điều 35 Bộ luật Lao động 2019" in all_queries
    assert "Điều 40 Bộ luật Lao động 2019" in all_queries
    assert "Điều 48 Bộ luật Lao động 2019" in all_queries
    assert "Điều 97 Bộ luật Lao động 2019" in all_queries
    assert "Điều 35" in vector_store.payload_terms_seen
    assert "Điều 40" in vector_store.payload_terms_seen
    assert "Điều 48" in vector_store.payload_terms_seen
    assert "Điều 97" in vector_store.payload_terms_seen
    assert "45/2019/QH14" in vector_store.payload_document_numbers


def test_pipeline_pins_explicit_document_and_article_citations() -> None:
    article_8 = SourceReference(
        document_id=180273,
        chunk_id="180273:8",
        title="Nghị định số 219/2025/NĐ-CP",
        document_number="219/2025/NĐ-CP",
        article_number="8",
        legal_path="Chương II > Điều 8. Hồ sơ đề nghị cấp giấy phép lao động",
        score=0,
        text="Điều 8. Hồ sơ đề nghị cấp giấy phép lao động. 1. Văn bản đề nghị cấp giấy phép lao động...",
    )
    article_18 = SourceReference(
        document_id=180273,
        chunk_id="180273:18",
        title="Nghị định số 219/2025/NĐ-CP",
        document_number="219/2025/NĐ-CP",
        article_number="18",
        clause_number="6",
        legal_path="Chương IV > Điều 18. Thành phần hồ sơ",
        score=0,
        text="Điều 18. Thành phần hồ sơ. 6. Văn bản của người sử dụng lao động tại nước ngoài...",
    )
    unrelated = SourceReference(
        document_id=1,
        chunk_id="1:1",
        title="Văn bản khác",
        document_number="01/2020/NĐ-CP",
        score=50,
        text="Không liên quan",
    )

    class ExplicitCitationVectorStore(FakeVectorStore):
        def search(self, _vector, limit, filters, issued_date_lte=None):
            _ = (limit, filters, issued_date_lte)
            return [unrelated]

    vector_store = ExplicitCitationVectorStore()
    vector_store.document_chunks_by_number["219/2025/NĐ-CP"] = [article_8, article_18]
    pipeline = RagPipeline(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question="Áp dụng Điều 8 và Điều 18 Nghị định số 219/2025/NĐ-CP như thế nào?",
                top_k=5,
            )
        )
    )

    chunk_ids = [reference.chunk_id for reference in response.references]
    assert chunk_ids[:2] == ["180273:8", "180273:18"]
    assert response.references[0].article_number == "8"
    assert response.references[1].article_number == "18"


def test_pipeline_expands_labor_code_hit_to_articles_35_40_48_97() -> None:
    employer_termination = SourceReference(
        document_id=139264,
        chunk_id="139264:26",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        validity_status="Hết hiệu lực một phần",
        score=20,
        text="Điều 36. Người sử dụng lao động phải báo trước 45 ngày.",
    )
    article_35 = SourceReference(
        document_id=139264,
        chunk_id="139264:25",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        validity_status="Hết hiệu lực một phần",
        score=2,
        text=(
            "Điều 35. Người lao động có quyền đơn phương chấm dứt hợp đồng lao động "
            "không cần báo trước nếu không được bố trí theo đúng công việc, địa điểm làm việc "
            "hoặc không được trả đủ lương hoặc trả lương không đúng thời hạn."
        ),
    )
    article_40 = SourceReference(
        document_id=139264,
        chunk_id="139264:30",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        validity_status="Hết hiệu lực một phần",
        score=2,
        text=(
            "Điều 40. Nghĩa vụ của người lao động khi đơn phương chấm dứt hợp đồng lao động "
            "trái pháp luật: không được trợ cấp thôi việc, bồi thường nửa tháng tiền lương và "
            "tiền lương trong những ngày không báo trước."
        ),
    )
    article_48 = SourceReference(
        document_id=139264,
        chunk_id="139264:42",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        validity_status="Hết hiệu lực một phần",
        score=2,
        text=(
            "Điều 48. Hai bên thanh toán đầy đủ các khoản tiền có liên quan đến quyền lợi của mỗi bên. "
            "Người sử dụng lao động hoàn thành thủ tục xác nhận thời gian đóng bảo hiểm xã hội, "
            "bảo hiểm thất nghiệp và trả lại cùng với bản chính giấy tờ khác."
        ),
    )
    article_97 = SourceReference(
        document_id=139264,
        chunk_id="139264:70",
        title="Bộ Luật lao động số 45/2019/QH14",
        document_number="45/2019/QH14",
        validity_status="Hết hiệu lực một phần",
        score=2,
        text=(
            "Điều 97. Người sử dụng lao động phải trả lương đúng hạn. Trường hợp bất khả kháng "
            "không được chậm quá 30 ngày và nếu trả lương chậm từ 15 ngày trở lên thì phải trả thêm."
        ),
    )

    class LaborVectorStore(FakeVectorStore):
        def search(self, _vector, limit, filters, issued_date_lte=None):
            _ = (limit, filters, issued_date_lte)
            return [employer_termination]

        def search_payload_text(self, terms, limit, issued_date_lte=None, document_numbers=None):
            super().search_payload_text(terms, limit, issued_date_lte, document_numbers)
            return []

    vector_store = LaborVectorStore()
    vector_store.document_chunks_by_id[139264] = [
        article_35,
        employer_termination,
        article_40,
        article_48,
        article_97,
    ]
    pipeline = RagPipeline(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=vector_store,
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question=(
                    "Công ty trả lương trễ hơn 20 ngày, đổi địa điểm làm việc, tôi nghỉ ngay "
                    "không báo trước, công ty giữ lương, không chốt BHXH và đòi bồi thường nửa tháng."
                ),
                top_k=5,
            )
        )
    )

    chunk_ids = [reference.chunk_id for reference in response.references]
    assert "139264:25" in chunk_ids
    assert "139264:30" in chunk_ids
    assert "139264:42" in chunk_ids
    assert "139264:70" in chunk_ids


def test_pipeline_strips_user_facing_self_check_from_answer() -> None:
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=FakeEmbeddingModel(),
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(["Kết luận chính.\n\n**Tự kiểm tra:** đã đủ ý."]),
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="Tư vấn thuế TNCN chuyển nhượng nhà ở", top_k=5))
    )

    assert response.answer == "Kết luận chính."


def test_pipeline_retries_when_answer_looks_truncated() -> None:
    llm_client = FakeLlmClient(["Câu trả lời cũng có thể", "Câu trả lời hoàn chỉnh."])
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=FakeEmbeddingModel(),
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=llm_client,
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="Tư vấn thuế TNCN chuyển nhượng nhà ở", top_k=5))
    )

    assert response.answer == "Câu trả lời hoàn chỉnh."
    assert len(llm_client.prompts) == 2
    assert "trả lời lại ngắn hơn" in llm_client.prompts[1]


def test_pipeline_retries_when_citation_verifier_fails_and_second_answer_succeeds() -> None:
    article = labor_article_35()

    class LaborVectorStore(FakeVectorStore):
        def search(self, _vector, limit, filters, issued_date_lte=None):
            _ = (limit, filters, issued_date_lte)
            return [article]

    llm_client = FakeLlmClient(
        [
            "Điều 999 cho phép người lao động nghỉ ngay khi chậm lương [1].",
            "Điều 35 cho phép người lao động nghỉ ngay nếu không được trả lương đúng hạn [1].",
        ]
    )
    pipeline = RagPipeline(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=LaborVectorStore(),
        reranker=FakeReranker(),
        llm_client=llm_client,
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="Tôi bị chậm lương, có được nghỉ ngay không?", top_k=5))
    )

    assert response.answer == (
        "Điều 35 cho phép người lao động nghỉ ngay nếu không được trả lương đúng hạn [1]."
    )
    assert len(llm_client.prompts) == 2
    assert "Phản hồi kiểm chứng có cấu trúc" in llm_client.prompts[1]
    assert "Điều 999" in llm_client.prompts[1]
    assert response.citation_verifier
    assert response.citation_verifier["passed"] is True


def test_pipeline_returns_safe_answer_when_citation_retry_still_fails() -> None:
    article = labor_article_35()

    class LaborVectorStore(FakeVectorStore):
        def search(self, _vector, limit, filters, issued_date_lte=None):
            _ = (limit, filters, issued_date_lte)
            return [article]

    llm_client = FakeLlmClient(
        [
            "Điều 999 cho phép người lao động nghỉ ngay khi chậm lương [1].",
            "Điều 998 vẫn cho phép người lao động nghỉ ngay khi chậm lương [1].",
        ]
    )
    pipeline = RagPipeline(
        Settings(embedding_dimension=2, enable_reranker=False),
        embedding_model=FakeEmbeddingModel(),
        vector_store=LaborVectorStore(),
        reranker=FakeReranker(),
        llm_client=llm_client,
    )

    response = asyncio.run(
        pipeline.ask(AskRequest(question="Tôi bị chậm lương, có được nghỉ ngay không?", top_k=5))
    )

    assert response.answer.startswith("Chưa đủ căn cứ đáng tin cậy")
    assert len(llm_client.prompts) == 2
    assert response.citation_verifier
    assert response.citation_verifier["passed"] is False
    assert "Điều 998" in response.citation_verifier["invented_references"]


def test_valid_as_of_allows_partially_expired_sources_but_excludes_fully_expired() -> None:
    partial = SourceReference(
        document_id=1,
        chunk_id="1:1",
        validity_status="Hết hiệu lực một phần",
        effective_date="2013-10-01",
        expired_date=None,
        score=1,
        text="Thông tư 111",
    )
    full = SourceReference(
        document_id=2,
        chunk_id="2:1",
        validity_status="Hết hiệu lực toàn bộ",
        effective_date="2009-10-01",
        expired_date="2013-10-01",
        score=1,
        text="Thông tư cũ",
    )

    assert RagPipeline._is_valid_as_of(partial, date(2026, 6, 30)) is True
    assert RagPipeline._is_valid_as_of(full, date(2026, 6, 30)) is False


def test_pipeline_classifies_land_transfer_sub_issue() -> None:
    pipeline = RagPipeline(
        Settings(embedding_dimension=2),
        embedding_model=FakeEmbeddingModel(),
        vector_store=FakeVectorStore(),
        reranker=FakeReranker(),
        llm_client=FakeLlmClient(),
    )

    response = asyncio.run(
        pipeline.ask(
            AskRequest(
                question="Thủ tục sang tên khi chuyển nhượng quyền sử dụng đất gồm hồ sơ gì?",
                top_k=5,
            )
        )
    )

    assert response.classification == "land_housing.transfer"
