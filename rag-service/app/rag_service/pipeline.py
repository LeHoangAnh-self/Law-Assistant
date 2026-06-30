import re
from datetime import date

from rag_service.config import Settings
from rag_service.embedding import EmbeddingModel
from rag_service.llm import LlmClient
from rag_service.models import AskRequest, AskResponse
from rag_service.prompting import build_legal_prompt
from rag_service.reranking import CrossEncoderReranker
from rag_service.vector_store import QdrantVectorStore


class RagPipeline:
    ISSUE_LABELS = {
        "tax.pit_real_estate_exemption": "tax: PIT real-estate transfer exemption",
        "tax.vat_invoice": "tax: VAT invoice",
        "tax.tax_penalty": "tax: tax penalty",
        "labor.resignation": "labor: resignation",
        "labor.salary": "labor: salary",
        "labor.discipline": "labor: discipline",
        "labor.termination": "labor: termination",
        "land_housing.red_book": "land/housing: red book",
        "land_housing.transfer": "land/housing: transfer",
        "land_housing.inheritance": "land/housing: inheritance",
        "land_housing.co_ownership": "land/housing: co-ownership",
        "civil.contracts": "civil: contracts",
        "civil.deposits": "civil: deposits",
        "civil.damages": "civil: damages",
        "enterprise.company_formation": "enterprise: company formation",
        "enterprise.capital_contribution": "enterprise: capital contribution",
        "enterprise.representative_authority": "enterprise: representative authority",
        "administrative_penalties.traffic": "administrative penalties: traffic",
        "administrative_penalties.construction": "administrative penalties: construction",
        "administrative_penalties.tax_penalties": "administrative penalties: tax penalties",
        "social_insurance.benefits": "social insurance: benefits",
        "social_insurance.contribution": "social insurance: contribution",
        "social_insurance.claim_procedures": "social insurance: claim procedures",
        "validity": "document validity",
        "relationship": "document relationship",
        "legal_research": "general legal research",
    }

    def __init__(
        self,
        settings: Settings,
        embedding_model: EmbeddingModel | None = None,
        vector_store: QdrantVectorStore | None = None,
        reranker: CrossEncoderReranker | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_model = embedding_model or EmbeddingModel(
            settings.embedding_model_name,
            device=settings.embedding_device,
            batch_size=settings.embedding_batch_size,
            local_files_only=settings.embedding_local_files_only,
        )
        self.vector_store = vector_store or QdrantVectorStore(
            str(settings.qdrant_url),
            settings.qdrant_collection,
            settings.embedding_dimension,
        )
        self.reranker = reranker or CrossEncoderReranker(
            settings.reranker_model_name,
            settings.enable_reranker,
        )
        self.llm_client = llm_client or LlmClient(
            provider=settings.llm_provider,
            api_type=settings.llm_api_type,
            api_base_url=settings.llm_api_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            reasoning_effort=settings.llm_reasoning_effort,
            max_output_tokens=settings.llm_max_output_tokens,
        )

    async def ask(self, request: AskRequest) -> AskResponse:
        rewritten_query = self._rewrite_query(request.question)
        classification = self._classify_question(rewritten_query)
        as_of_date = request.retrieval_cutoff_date or self._extract_as_of_date(rewritten_query)
        retrieval_queries = self._build_retrieval_queries(rewritten_query, classification)
        candidates = self._retrieve_candidates(
            retrieval_queries,
            filters=request.filters,
            as_of_date=as_of_date,
        )
        candidates.extend(
            self._retrieve_must_have_sources(
                rewritten_query,
                classification=classification,
                as_of_date=as_of_date,
            )
        )
        candidates = self._dedupe_candidates(candidates)
        candidates.extend(
            self._expand_adjacent_sections(
                candidates,
                rewritten_query,
                classification=classification,
                as_of_date=as_of_date,
            )
        )
        candidates = self._dedupe_candidates(candidates)
        candidates = self._prefer_valid_as_of(candidates, as_of_date, request.top_k)
        retrieval_query = "\n---\n".join(retrieval_queries)
        references = self.reranker.rerank(retrieval_query, candidates, limit=request.top_k)
        references = self._ensure_required_references(
            references,
            candidates,
            rewritten_query,
            classification=classification,
            limit=request.top_k,
        )
        required_source_checklist = self._required_source_checklist(rewritten_query, classification)
        missing_required_sources = self._missing_required_source_labels(rewritten_query, classification, references)
        prompt = build_legal_prompt(
            request.question,
            references,
            answer_language=self.settings.answer_language,
            conversation_context=request.conversation_context,
            as_of_date=as_of_date,
            issue_label=self.ISSUE_LABELS.get(classification, classification),
            required_source_checklist=required_source_checklist,
            missing_required_sources=missing_required_sources,
        )
        answer = await self.llm_client.generate(prompt)
        if not self._looks_complete(answer):
            answer = await self.llm_client.generate(
                f"{prompt}\n\n"
                "Lần trả lời trước có dấu hiệu bị cắt giữa chừng. Hãy trả lời lại ngắn hơn, "
                "đầy đủ, kết thúc sạch, tối đa 650 từ."
            )
        answer = self._strip_user_facing_self_check(answer)
        return AskResponse(
            answer=answer,
            rewritten_query=rewritten_query,
            classification=classification,
            references=references,
            retrieval_query=retrieval_query,
        )

    @staticmethod
    def _rewrite_query(question: str) -> str:
        return " ".join(question.strip().split())

    @staticmethod
    def _classify_question(question: str) -> str:
        lowered = question.lower()
        if any(term in lowered for term in ["tncn", "thu nhập cá nhân"]) and any(
            term in lowered for term in ["bất động sản", "nhà ở", "đất ở", "chuyển nhượng", "căn hộ"]
        ):
            return "tax.pit_real_estate_exemption" if any(
                term in lowered for term in ["miễn", "duy nhất"]
            ) else "tax.tax_penalty"
        if any(term in lowered for term in ["hóa đơn", "vat", "gtgt", "giá trị gia tăng"]):
            return "tax.vat_invoice"
        if any(term in lowered for term in ["xử phạt thuế", "phạt thuế", "trốn thuế", "tax penalty"]):
            return "tax.tax_penalty"
        if any(
            term in lowered
            for term in [
                "lao động",
                "hợp đồng lao động",
                "nghỉ việc",
                "báo trước",
                "trả lương",
                "chốt sổ bhxh",
                "bảo hiểm xã hội",
                "người lao động",
                "người sử dụng lao động",
            ]
        ):
            if any(term in lowered for term in ["nghỉ việc", "đơn phương", "báo trước"]):
                return "labor.resignation"
            if any(term in lowered for term in ["lương", "chậm lương", "nợ lương"]):
                return "labor.salary"
            if any(term in lowered for term in ["kỷ luật", "sa thải"]):
                return "labor.discipline"
            return "labor.termination"
        if any(term in lowered for term in ["sổ đỏ", "sổ hồng", "giấy chứng nhận"]):
            return "land_housing.red_book"
        if any(term in lowered for term in ["chuyển nhượng đất", "sang tên", "chuyển nhượng quyền sử dụng đất"]):
            return "land_housing.transfer"
        if any(term in lowered for term in ["thừa kế", "di chúc", "hàng thừa kế"]):
            return "land_housing.inheritance"
        if any(term in lowered for term in ["đồng sở hữu", "đứng tên chung", "sở hữu chung"]):
            return "land_housing.co_ownership"
        if any(term in lowered for term in ["hợp đồng", "giao kết", "điều khoản"]):
            return "civil.contracts"
        if any(term in lowered for term in ["đặt cọc", "tiền cọc"]):
            return "civil.deposits"
        if any(term in lowered for term in ["bồi thường", "thiệt hại", "damages"]):
            return "civil.damages"
        if any(term in lowered for term in ["thành lập công ty", "đăng ký doanh nghiệp", "company formation"]):
            return "enterprise.company_formation"
        if any(term in lowered for term in ["góp vốn", "vốn điều lệ", "capital contribution"]):
            return "enterprise.capital_contribution"
        if any(term in lowered for term in ["người đại diện", "đại diện theo pháp luật", "representative authority"]):
            return "enterprise.representative_authority"
        if any(term in lowered for term in ["phạt nguội", "giao thông", "traffic"]):
            return "administrative_penalties.traffic"
        if any(term in lowered for term in ["trật tự xây dựng", "xây dựng không phép", "construction penalty"]):
            return "administrative_penalties.construction"
        if any(term in lowered for term in ["xử phạt vi phạm hành chính về thuế", "tax administrative penalty"]):
            return "administrative_penalties.tax_penalties"
        if any(term in lowered for term in ["bhxh", "bảo hiểm xã hội", "ốm đau", "thai sản", "hưu trí"]):
            if any(term in lowered for term in ["mức đóng", "truy đóng", "đóng bhxh"]):
                return "social_insurance.contribution"
            if any(term in lowered for term in ["thủ tục", "hồ sơ", "quy trình", "claim"]):
                return "social_insurance.claim_procedures"
            return "social_insurance.benefits"
        if any(term in lowered for term in ["thuế", "tax"]):
            return "tax.tax_penalty"
        if any(
            term in lowered
            for term in ["expire", "valid", "effective", "hiệu lực", "hết hiệu lực", "còn hiệu lực"]
        ):
            return "validity"
        if any(
            term in lowered
            for term in ["amend", "replace", "relationship", "sửa đổi", "thay thế", "bổ sung"]
        ):
            return "relationship"
        return "legal_research"

    @staticmethod
    def _build_retrieval_queries(question: str, classification: str) -> list[str]:
        lowered = question.lower()
        queries = [question]
        if classification.startswith("tax."):
            queries.append("Luật Thuế thu nhập cá nhân hiện hành miễn thuế thu nhập cá nhân chuyển nhượng bất động sản")
        if any(term in lowered for term in ["miễn", "duy nhất", "nhà ở duy nhất", "đất ở duy nhất"]):
            queries.extend(
                [
                    "miễn thuế TNCN chuyển nhượng nhà ở duy nhất quyền sử dụng đất ở duy nhất",
                    "Thông tư 111/2013/TT-BTC Điều 3 nhà ở duy nhất đất ở duy nhất miễn thuế",
                    "Luật Thuế thu nhập cá nhân Điều 4 miễn thuế chuyển nhượng nhà ở đất ở duy nhất",
                    "hồ sơ miễn thuế TNCN chuyển nhượng nhà ở duy nhất cam kết nhà đất duy nhất",
                ]
            )
        if any(term in lowered for term in ["vợ chồng", "đồng sở hữu", "đứng tên chung", "cùng đứng tên"]):
            queries.extend(
                [
                    "chuyển nhượng nhà đất đồng sở hữu vợ chồng miễn thuế TNCN",
                    "mỗi cá nhân đồng sở hữu bất động sản xác định nghĩa vụ thuế theo phần sở hữu",
                    "vợ chồng đồng sở hữu một người có nhà đất riêng miễn thuế nhà ở duy nhất",
                    "Thông tư 111/2013/TT-BTC Điều 12 đồng sở hữu nghĩa vụ thuế tỷ lệ bình quân",
                ]
            )
        if any(term in lowered for term in ["bất động sản", "nhà đất", "chuyển nhượng đất", "căn hộ"]):
            queries.append("chuyển nhượng bất động sản cá nhân cư trú thuế TNCN miễn thuế nhà ở duy nhất")
        if classification.startswith("labor."):
            queries.append("Bộ luật Lao động 2019 người lao động đơn phương chấm dứt hợp đồng lao động")
            if any(term in lowered for term in ["nghỉ", "nghỉ việc", "báo trước", "45 ngày"]):
                queries.extend(
                    [
                        "Điều 35 Bộ luật Lao động 2019 người lao động đơn phương chấm dứt hợp đồng không cần báo trước",
                        "Điều 35 Bộ luật Lao động 2019 không được trả lương đầy đủ đúng hạn không cần báo trước",
                        "Điều 35 Bộ luật Lao động 2019 không được bố trí đúng công việc địa điểm làm việc điều kiện làm việc đã thỏa thuận",
                        "Điều 35 Bộ luật Lao động 2019 trả lương không đúng thời hạn địa điểm làm việc không đúng thỏa thuận không cần báo trước",
                    ]
                )
            if any(term in lowered for term in ["trái luật", "bồi thường", "nửa tháng", "không báo trước"]):
                queries.append("Điều 40 Bộ luật Lao động 2019 nghĩa vụ người lao động đơn phương chấm dứt hợp đồng trái pháp luật")
            if any(term in lowered for term in ["giữ lương", "lương tháng cuối", "chốt sổ", "bhxh", "bảo hiểm xã hội"]):
                queries.append("Điều 48 Bộ luật Lao động 2019 thanh toán lương xác nhận thời gian đóng bảo hiểm xã hội khi chấm dứt hợp đồng")
            if any(term in lowered for term in ["trả lương trễ", "trả lương chậm", "trễ hơn", "chậm lương"]):
                queries.append("Điều 97 Bộ luật Lao động 2019 trả lương chậm quá 15 ngày đền bù lãi")
        if classification == "land_housing.transfer":
            queries.extend(
                [
                    "Luật Đất đai chuyển nhượng quyền sử dụng đất điều kiện thực hiện quyền",
                    "đăng ký biến động sang tên quyền sử dụng đất hồ sơ thủ tục",
                    "thuế thu nhập cá nhân lệ phí trước bạ khi chuyển nhượng quyền sử dụng đất",
                ]
            )
        if len(queries) == 1 and classification.startswith("tax."):
            queries.append("Luật Thuế thu nhập cá nhân hiện hành căn cứ tính thuế thuế suất")
        return list(dict.fromkeys(queries))

    def _retrieve_candidates(
        self,
        retrieval_queries: list[str],
        filters: dict[str, str],
        as_of_date: date | None,
    ):
        by_chunk_id = {}
        per_query_limit = max(8, min(self.settings.retrieval_limit, 24))
        for query in retrieval_queries:
            embedding_query = f"{self.settings.embedding_query_instruction}{query}"
            query_vector = self.embedding_model.embed_one(embedding_query)
            hits = self.vector_store.search(
                query_vector,
                limit=per_query_limit,
                filters=filters,
                issued_date_lte=as_of_date,
            )
            for hit in hits:
                previous = by_chunk_id.get(hit.chunk_id)
                if previous is None or hit.score > previous.score:
                    by_chunk_id[hit.chunk_id] = hit
        return sorted(by_chunk_id.values(), key=lambda reference: reference.score, reverse=True)[
            : self.settings.retrieval_limit
        ]

    def _retrieve_must_have_sources(
        self,
        question: str,
        classification: str,
        as_of_date: date | None,
    ):
        if not hasattr(self.vector_store, "search_payload_text"):
            return []
        lowered = question.lower()
        terms: list[str] = []
        if classification.startswith("tax.") and any(
            term in lowered for term in ["miễn", "duy nhất", "nhà ở duy nhất", "đất ở duy nhất"]
        ):
            terms.extend(
                [
                    "111/2013/TT-BTC",
                    "Thông tư 111/2013",
                    "nhà ở duy nhất",
                    "quyền sử dụng đất ở duy nhất",
                    "còn có nhà ở, đất ở riêng",
                    "vợ chồng có chung quyền sở hữu",
                    "miễn thuế",
                ]
            )
        if classification.startswith("tax.") and any(
            term in lowered for term in ["đồng sở hữu", "đứng tên chung", "vợ chồng"]
        ):
            terms.extend(
                [
                    "nghĩa vụ thuế được xác định riêng",
                    "tỷ lệ bình quân",
                    "từng cá nhân đồng sở hữu",
                    "đồng sở hữu",
                    "Điều 12",
                ]
            )
        if classification.startswith("labor."):
            terms.extend(self._labor_required_terms(question))
        if classification == "land_housing.transfer":
            terms.extend(
                [
                    "Luật Đất đai",
                    "điều kiện thực hiện quyền chuyển nhượng quyền sử dụng đất",
                    "đăng ký biến động",
                    "lệ phí trước bạ",
                    "thuế thu nhập cá nhân",
                ]
            )
        if not terms:
            return []
        issue_is_only_home_coowner = self._is_only_home_coowner_issue(question, classification)
        general_matches = []
        if not issue_is_only_home_coowner and not classification.startswith("labor."):
            general_matches = self.vector_store.search_payload_text(
                terms=list(dict.fromkeys(terms)),
                limit=12,
                issued_date_lte=as_of_date,
            )
        circular_111_matches = []
        if classification.startswith("tax."):
            circular_111_terms = [
                "Điều 3",
                "Điều 12",
                "nhà ở duy nhất",
                "quyền sử dụng đất ở duy nhất",
                "vợ chồng có chung quyền sở hữu",
                "còn có nhà ở, đất ở riêng",
                "nghĩa vụ thuế được xác định riêng",
                "tỷ lệ bình quân",
                "đồng sở hữu",
            ]
            if issue_is_only_home_coowner:
                circular_111_terms.extend(
                    [
                        "chồng hoặc vợ có nhà ở, đất ở riêng không được miễn thuế",
                        "thu nhập từ chuyển nhượng bất động sản",
                        "trường hợp bất động sản thuộc sở hữu chung",
                        "trường hợp không có tài liệu hợp pháp thì nghĩa vụ thuế",
                    ]
                )
            circular_111_matches = self.vector_store.search_payload_text(
                terms=circular_111_terms,
                limit=20 if issue_is_only_home_coowner else 12,
                issued_date_lte=as_of_date,
                document_numbers=["111/2013/TT-BTC"],
            )
        labor_matches = []
        if classification.startswith("labor."):
            labor_matches = self.vector_store.search_payload_text(
                terms=self._labor_required_terms(question),
                limit=24,
                issued_date_lte=as_of_date,
                document_numbers=["45/2019/QH14"],
            )
        return general_matches + circular_111_matches + labor_matches

    def _expand_adjacent_sections(
        self,
        candidates,
        question: str,
        classification: str,
        as_of_date: date | None,
    ):
        if not hasattr(self.vector_store, "get_document_chunks"):
            return []
        expansions = []
        issue_is_only_home_coowner = self._is_only_home_coowner_issue(question, classification)
        for candidate in candidates[:12]:
            if classification.startswith("labor.") and self._is_labor_code_2019(candidate):
                chunks = self.vector_store.get_document_chunks(candidate.document_id, issued_date_lte=as_of_date)
                expansions.extend(self.vector_store.get_adjacent_chunks(chunks, candidate.chunk_id, window=1))
                expansions.extend(self._find_required_labor_sources(chunks, question))
                continue
            if self._looks_like_article_chunk(candidate):
                chunks = self.vector_store.get_document_chunks(candidate.document_id, issued_date_lte=as_of_date)
                expansions.extend(self.vector_store.get_adjacent_chunks(chunks, candidate.chunk_id, window=1))
            if not self._is_circular_111(candidate):
                continue
            text = self._reference_haystack(candidate)
            if "nhà ở duy nhất" not in text and "đất ở duy nhất" not in text and "điều 3" not in text:
                continue
            if issue_is_only_home_coowner:
                chunks = self.vector_store.get_document_chunks(candidate.document_id, issued_date_lte=as_of_date)
                expansions.extend(self._find_required_circular_111_sources(chunks, article_12=True))
        return expansions

    def _ensure_required_references(
        self,
        references,
        candidates,
        question: str,
        classification: str,
        limit: int,
    ):
        if not self._is_only_home_coowner_issue(question, classification):
            if classification.startswith("labor."):
                return self._ensure_required_labor_references(references, candidates, question, limit)
            return references
        required = self._find_required_circular_111_sources(candidates, article_12=True)
        required.extend(self._find_required_circular_111_sources(candidates, article_3=True))
        if not required:
            return references
        by_chunk_id = {reference.chunk_id: reference for reference in references}
        merged = list(references)
        for reference in required:
            if reference.chunk_id not in by_chunk_id:
                merged.append(reference)
                by_chunk_id[reference.chunk_id] = reference
        if len(merged) <= limit:
            return merged

        required_ids = {reference.chunk_id for reference in required}
        kept_required = [reference for reference in merged if reference.chunk_id in required_ids]
        kept_optional = [reference for reference in merged if reference.chunk_id not in required_ids]
        return (kept_required + kept_optional)[:limit]

    def _ensure_required_labor_references(self, references, candidates, question: str, limit: int):
        required = self._find_required_labor_sources(candidates, question)
        if not required:
            return references
        by_chunk_id = {reference.chunk_id: reference for reference in references}
        merged = list(references)
        for reference in required:
            if reference.chunk_id not in by_chunk_id:
                merged.append(reference)
                by_chunk_id[reference.chunk_id] = reference
        if len(merged) <= limit:
            return merged
        required_ids = {reference.chunk_id for reference in required}
        kept_required = [reference for reference in merged if reference.chunk_id in required_ids]
        kept_optional = [reference for reference in merged if reference.chunk_id not in required_ids]
        return (kept_required + kept_optional)[:limit]

    @classmethod
    def _find_required_labor_sources(cls, references, question: str):
        lowered = question.lower()
        wanted_articles = {"35"}
        if any(term in lowered for term in ["trái luật", "bồi thường", "nửa tháng", "không báo trước"]):
            wanted_articles.add("40")
        if any(term in lowered for term in ["giữ lương", "lương tháng cuối", "chốt sổ", "bhxh", "bảo hiểm xã hội"]):
            wanted_articles.add("48")
        if any(term in lowered for term in ["trả lương trễ", "trả lương chậm", "trễ hơn", "chậm lương"]):
            wanted_articles.add("97")

        matches = []
        for reference in references:
            if not cls._is_labor_code_2019(reference):
                continue
            haystack = cls._reference_haystack(reference)
            for article in wanted_articles:
                if f"điều {article}" in haystack or cls._matches_labor_article_content(article, haystack):
                    matches.append(reference)
                    break
        return matches

    @staticmethod
    def _matches_labor_article_content(article: str, haystack: str) -> bool:
        if article == "35":
            return (
                "người lao động có quyền đơn phương chấm dứt hợp đồng lao động" in haystack
                and (
                    "không cần báo trước" in haystack
                    or "không được bố trí theo đúng công việc" in haystack
                    or "không được trả đủ lương" in haystack
                    or "trả lương không đúng thời hạn" in haystack
                )
            )
        if article == "40":
            return (
                "nghĩa vụ của người lao động khi đơn phương chấm dứt hợp đồng lao động trái pháp luật" in haystack
                or ("nửa tháng tiền lương" in haystack and "ngày không báo trước" in haystack)
            )
        if article == "48":
            return (
                "thanh toán đầy đủ các khoản tiền có liên quan đến quyền lợi của mỗi bên" in haystack
                or "hoàn thành thủ tục xác nhận thời gian đóng bảo hiểm xã hội" in haystack
                or ("bảo hiểm thất nghiệp" in haystack and "trả lại cùng với bản chính giấy tờ" in haystack)
            )
        if article == "97":
            return (
                "trả lương đúng hạn" in haystack
                or ("không được chậm quá 30 ngày" in haystack and "trả thêm cho người lao động" in haystack)
                or ("chậm trả lương" in haystack and "đền bù" in haystack)
            )
        return False

    @classmethod
    def _find_required_circular_111_sources(
        cls,
        references,
        article_3: bool = False,
        article_12: bool = False,
    ):
        matches = []
        for reference in references:
            if not cls._is_circular_111(reference):
                continue
            haystack = cls._reference_haystack(reference)
            if article_3 and (
                ("nhà ở duy nhất" in haystack or "đất ở duy nhất" in haystack)
                and ("chồng hoặc vợ" in haystack or "vợ chồng" in haystack or "183 ngày" in haystack)
            ):
                matches.append(reference)
            if article_12 and (
                "đồng sở hữu" in haystack
                or "sở hữu chung" in haystack
                or "tỷ lệ bình quân" in haystack
                or "nghĩa vụ thuế được xác định riêng" in haystack
                or "trường hợp không có tài liệu hợp pháp" in haystack
            ):
                matches.append(reference)
        return matches

    @staticmethod
    def _is_only_home_coowner_issue(question: str, classification: str) -> bool:
        lowered = question.lower()
        return (
            classification.startswith("tax.")
            and any(term in lowered for term in ["miễn", "duy nhất", "nhà ở duy nhất", "đất ở duy nhất"])
            and any(term in lowered for term in ["đồng sở hữu", "đứng tên chung", "vợ chồng", "cùng đứng tên"])
        )

    @staticmethod
    def _looks_like_article_chunk(reference) -> bool:
        haystack = " ".join(
            value or ""
            for value in [reference.legal_path, reference.article_number, reference.text[:300]]
        ).lower()
        return "điều " in haystack

    @staticmethod
    def _is_circular_111(reference) -> bool:
        haystack = " ".join([reference.document_number or "", reference.title or ""]).lower()
        return "111/2013/tt-btc" in haystack or "thông tư 111/2013" in haystack

    @staticmethod
    def _is_labor_code_2019(reference) -> bool:
        haystack = " ".join([reference.document_number or "", reference.title or ""]).lower()
        return "45/2019/qh14" in haystack or "bộ luật lao động" in haystack

    @staticmethod
    def _labor_required_terms(question: str) -> list[str]:
        lowered = question.lower()
        terms = [
            "Bộ luật Lao động",
            "45/2019/QH14",
            "Điều 35",
            "người lao động có quyền đơn phương chấm dứt hợp đồng lao động",
            "không cần báo trước",
            "không được bố trí theo đúng công việc, địa điểm làm việc",
            "không được trả đủ lương hoặc trả lương không đúng thời hạn",
        ]
        if any(term in lowered for term in ["trái luật", "bồi thường", "nửa tháng", "không báo trước"]):
            terms.extend(
                [
                    "Điều 40",
                    "nghĩa vụ của người lao động khi đơn phương chấm dứt hợp đồng lao động trái pháp luật",
                    "phải bồi thường cho người sử dụng lao động nửa tháng tiền lương",
                    "một khoản tiền tương ứng với tiền lương theo hợp đồng lao động trong những ngày không báo trước",
                ]
            )
        if any(term in lowered for term in ["giữ lương", "lương tháng cuối", "chốt sổ", "bhxh", "bảo hiểm xã hội"]):
            terms.extend(
                [
                    "Điều 48",
                    "trách nhiệm khi chấm dứt hợp đồng lao động",
                    "thanh toán đầy đủ các khoản tiền có liên quan đến quyền lợi của mỗi bên",
                    "xác nhận thời gian đóng bảo hiểm xã hội",
                    "bảo hiểm thất nghiệp và trả lại cùng với bản chính giấy tờ khác",
                ]
            )
        if any(term in lowered for term in ["trả lương trễ", "trả lương chậm", "trễ hơn", "chậm lương"]):
            terms.extend(
                [
                    "Điều 97",
                    "trường hợp vì lý do bất khả kháng mà người sử dụng lao động đã tìm mọi biện pháp khắc phục",
                    "không được chậm quá 30 ngày",
                    "trả thêm cho người lao động một khoản tiền",
                ]
            )
        return terms

    @classmethod
    def _required_source_checklist(cls, question: str, classification: str) -> list[str]:
        if classification.startswith("labor."):
            return [
                "Bộ luật Lao động 2019 Điều 35 (quyền nghỉ việc của NLĐ)",
                "Bộ luật Lao động 2019 Điều 40 (nghĩa vụ khi nghỉ trái pháp luật)",
                "Bộ luật Lao động 2019 Điều 48 (thanh toán quyền lợi, xác nhận BHXH/BHTN)",
                "Bộ luật Lao động 2019 Điều 97 (trả lương đúng hạn, bồi hoàn khi chậm lương)",
            ]
        if cls._is_only_home_coowner_issue(question, classification):
            return [
                "Thông tư 111/2013/TT-BTC Điều 3 (miễn thuế TNCN nhà ở/đất ở duy nhất)",
                "Thông tư 111/2013/TT-BTC Điều 12 (phân bổ nghĩa vụ thuế theo đồng sở hữu)",
            ]
        if classification == "land_housing.transfer":
            return [
                "Luật Đất đai: điều kiện chuyển nhượng quyền sử dụng đất",
                "Văn bản đăng ký đất đai: thủ tục đăng ký biến động/sang tên",
                "Văn bản thuế, phí: thuế TNCN và lệ phí trước bạ liên quan chuyển nhượng",
            ]
        if classification.startswith("social_insurance."):
            return [
                "Luật Bảo hiểm xã hội: nhóm điều khoản đúng chế độ đang hỏi",
                "Nghị định/Thông tư hướng dẫn thủ tục, hồ sơ và cơ quan giải quyết (nếu có)",
            ]
        return []

    @classmethod
    def _missing_required_source_labels(cls, question: str, classification: str, references) -> list[str]:
        checklist = cls._required_source_checklist(question, classification)
        if not checklist:
            return []
        haystacks = [cls._reference_haystack(reference) for reference in references]
        missing: list[str] = []
        for item in checklist:
            if "Điều 35" in item and not any("điều 35" in text for text in haystacks):
                missing.append(item)
            elif "Điều 40" in item and not any("điều 40" in text for text in haystacks):
                missing.append(item)
            elif "Điều 48" in item and not any("điều 48" in text for text in haystacks):
                missing.append(item)
            elif "Điều 97" in item and not any("điều 97" in text for text in haystacks):
                missing.append(item)
            elif "Điều 3" in item and not any("điều 3" in text and cls._is_circular_111_ref_text(text) for text in haystacks):
                missing.append(item)
            elif "Điều 12" in item and not any("điều 12" in text and cls._is_circular_111_ref_text(text) for text in haystacks):
                missing.append(item)
            elif "Luật Đất đai" in item and not any("luật đất đai" in text for text in haystacks):
                missing.append(item)
            elif "đăng ký biến động" in item and not any(
                phrase in text for text in haystacks for phrase in ["đăng ký biến động", "sang tên"]
            ):
                missing.append(item)
            elif "thuế TNCN" in item and not any(
                phrase in text
                for text in haystacks
                for phrase in ["thuế thu nhập cá nhân", "lệ phí trước bạ"]
            ):
                missing.append(item)
            elif "Luật Bảo hiểm xã hội" in item and not any("luật bảo hiểm xã hội" in text for text in haystacks):
                missing.append(item)
            elif "Nghị định/Thông tư" in item and not any(
                phrase in text
                for text in haystacks
                for phrase in ["nghị định", "thông tư", "quyết định"]
            ):
                missing.append(item)
        return missing

    @staticmethod
    def _is_circular_111_ref_text(text: str) -> bool:
        return "111/2013/tt-btc" in text or "thông tư 111/2013" in text

    @staticmethod
    def _reference_haystack(reference) -> str:
        return " ".join(
            value or ""
            for value in [
                reference.title,
                reference.document_number,
                reference.legal_path,
                reference.text,
            ]
        ).lower()

    @staticmethod
    def _dedupe_candidates(candidates):
        by_chunk_id = {}
        for candidate in candidates:
            previous = by_chunk_id.get(candidate.chunk_id)
            if previous is None or candidate.score > previous.score:
                by_chunk_id[candidate.chunk_id] = candidate
        return sorted(by_chunk_id.values(), key=lambda reference: reference.score, reverse=True)

    @staticmethod
    def _prefer_valid_as_of(candidates, as_of_date: date | None, top_k: int):
        if not as_of_date:
            return candidates
        valid = [candidate for candidate in candidates if RagPipeline._is_valid_as_of(candidate, as_of_date)]
        invalid = [candidate for candidate in candidates if candidate not in valid]
        if valid:
            return valid
        return valid + invalid[: max(0, top_k - len(valid))]

    @staticmethod
    def _is_valid_as_of(reference, as_of_date: date) -> bool:
        status = (reference.validity_status or "").lower()
        if "hết hiệu lực toàn bộ" in status or "chưa có hiệu lực" in status:
            return False
        effective_date = RagPipeline._parse_iso_date(reference.effective_date)
        expired_date = RagPipeline._parse_iso_date(reference.expired_date)
        issued_date = RagPipeline._parse_iso_date(reference.issued_date)
        if effective_date and effective_date > as_of_date:
            return False
        if not effective_date and issued_date and issued_date > as_of_date:
            return False
        if expired_date and expired_date <= as_of_date:
            return False
        return True

    @staticmethod
    def _extract_as_of_date(question: str) -> date | None:
        match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", question)
        if not match:
            return None
        day, month, year = (int(part) for part in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _parse_iso_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

    @staticmethod
    def _looks_complete(answer: str) -> bool:
        stripped = answer.strip()
        if len(stripped) < 20:
            return False
        if stripped.endswith(("...", "…", ",", ";", ":", "-", "—")):
            return False
        last_line = stripped.splitlines()[-1].strip().lower()
        if last_line in {"và", "hoặc", "cũng có thể", "câu trả lời cũng có thể"}:
            return False
        return stripped[-1] in ".!?。.!?)]}”\"'"

    @staticmethod
    def _strip_user_facing_self_check(answer: str) -> str:
        marker = re.search(r"(?im)^\s*(?:\*\*)?\s*Tự kiểm tra\s*(?:\*\*)?\s*:", answer)
        if not marker:
            return answer
        return answer[: marker.start()].rstrip()
