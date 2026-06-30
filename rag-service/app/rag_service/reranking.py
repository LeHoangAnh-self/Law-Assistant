from functools import cached_property
from datetime import date

from rag_service.models import SourceReference


class CrossEncoderReranker:
    def __init__(self, model_name: str, enabled: bool = True) -> None:
        self.model_name = model_name
        self.enabled = enabled

    @cached_property
    def _model(self):
        from sentence_transformers import CrossEncoder

        return CrossEncoder(self.model_name)

    def rerank(self, query: str, references: list[SourceReference], limit: int) -> list[SourceReference]:
        if not self.enabled or len(references) <= 1:
            return self._diversify(self._quality_adjusted(query, references), limit)
        pairs = [(query, reference.text) for reference in references]
        scores = self._model.predict(pairs)
        rescored = [
            reference.model_copy(update={"score": float(score)})
            for reference, score in zip(references, scores, strict=True)
        ]
        ranked = self._quality_adjusted(query, rescored)
        return self._diversify(ranked, limit)

    @classmethod
    def _quality_adjusted(
        cls,
        query: str,
        references: list[SourceReference],
    ) -> list[SourceReference]:
        adjusted = [
            reference.model_copy(update={"score": reference.score + cls._quality_bonus(query, reference)})
            for reference in references
        ]
        return sorted(adjusted, key=lambda reference: reference.score, reverse=True)

    @staticmethod
    def _quality_bonus(query: str, reference: SourceReference) -> float:
        lowered_query = query.lower()
        haystack = " ".join(
            value or ""
            for value in [
                reference.title,
                reference.document_number,
                reference.validity_status,
                reference.legal_path,
                reference.text[:1000],
            ]
        ).lower()
        bonus = 0.0

        if reference.validity_status and "hết hiệu lực toàn bộ" in reference.validity_status.lower():
            bonus -= 4.0
        elif reference.validity_status and "hết hiệu lực một phần" in reference.validity_status.lower():
            bonus -= 0.25
        if reference.validity_status and "chưa có hiệu lực" in reference.validity_status.lower():
            bonus -= 0.75

        issued_year = None
        if reference.issued_date:
            try:
                issued_year = date.fromisoformat(reference.issued_date[:10]).year
            except ValueError:
                issued_year = None

        is_current_tax_query = any(
            term in lowered_query
            for term in ["thuế", "tncn", "thu nhập cá nhân", "bất động sản", "chuyển nhượng"]
        )
        is_pit_real_estate_exemption_query = (
            any(term in lowered_query for term in ["tncn", "thu nhập cá nhân"])
            and any(term in lowered_query for term in ["bất động sản", "nhà ở", "đất ở", "căn hộ", "nhà đất"])
            and any(term in lowered_query for term in ["miễn", "duy nhất"])
        )
        if is_current_tax_query:
            if "thu nhập cao" in haystack or "pháp lệnh thuế thu nhập" in haystack:
                bonus -= 8.0
            if issued_year and issued_year < 2009:
                bonus -= 2.5
            if "luật thuế thu nhập cá nhân" in haystack:
                bonus += 2.0
            if "nghị định số 12/2015" in haystack or "12/2015/nđ-cp" in haystack:
                bonus += 2.0
            if "chuyển nhượng bất động sản" in haystack and "2%" in haystack:
                bonus += 3.0
            if "cá nhân không cư trú" in haystack and "không cư trú" not in lowered_query:
                bonus -= 5.0
            if any(term in haystack for term in ["kinh doanh bất động sản", "nhà ở xã hội", "dự án bất động sản"]):
                if any(term in lowered_query for term in ["miễn", "duy nhất", "tncn", "thu nhập cá nhân"]):
                    bonus -= 3.0
            if any(term in haystack for term in ["hải quan", "hàng miễn thuế", "miễn thuế nhập khẩu"]):
                bonus -= 8.0
            if "thuế sử dụng đất phi nông nghiệp" in haystack:
                bonus -= 8.0
            if any(term in haystack for term in ["thông tư 111/2013", "111/2013/tt-btc"]):
                bonus += 4.0
            if any(term in haystack for term in ["điều 3", "điểm b, khoản 1, điều này"]):
                if "nhà ở duy nhất" in lowered_query or "duy nhất" in lowered_query:
                    bonus += 3.0
            if "điều 12" in haystack and any(
                term in lowered_query for term in ["đồng sở hữu", "tỷ lệ bình quân", "nghĩa vụ thuế"]
            ):
                bonus += 5.0
            if any(term in haystack for term in ["nghị định 65/2013", "65/2013/nđ-cp"]):
                bonus += 2.5
            if "miễn thuế" in haystack:
                bonus += 2.5
            if "nhà ở duy nhất" in haystack or "đất ở duy nhất" in haystack:
                bonus += 5.0
            if any(term in haystack for term in ["đồng sở hữu", "sở hữu chung", "nhiều người cùng đứng tên"]):
                bonus += 2.5
            if "hồ sơ" in haystack and "miễn thuế" in haystack:
                bonus += 1.5
            if is_pit_real_estate_exemption_query:
                irrelevant_tax_topics = [
                    "hải quan",
                    "thuế nhập khẩu",
                    "thuế xuất khẩu",
                    "hàng miễn thuế",
                    "thương mại biên giới",
                    "cư dân biên giới",
                    "thuế tài nguyên",
                    "tiền lương, tiền công",
                    "phụ cấp",
                    "trợ cấp",
                    "thuế sử dụng đất phi nông nghiệp",
                    "thu nhập từ kinh doanh",
                    "sản xuất, kinh doanh nông nghiệp",
                    "lâm nghiệp",
                    "đánh bắt thủy sản",
                    "làm muối",
                ]
                if any(term in haystack for term in irrelevant_tax_topics):
                    bonus -= 10.0
                unrelated_exemption_terms = [
                    "định mức miễn thuế",
                    "miễn thuế nhập khẩu",
                    "miễn thuế tài nguyên",
                    "miễn thuế đối với hàng hóa",
                    "quà biếu, quà tặng hàng hóa",
                ]
                if any(term in haystack for term in unrelated_exemption_terms):
                    bonus -= 8.0

        is_labor_resignation_query = any(
            term in lowered_query
            for term in ["nghỉ việc", "báo trước", "chấm dứt hợp đồng lao động", "trái luật"]
        ) and any(term in lowered_query for term in ["lương", "địa điểm", "bhxh", "bảo hiểm xã hội"])
        if is_labor_resignation_query:
            if any(term in haystack for term in ["bộ luật lao động", "45/2019/qh14"]):
                bonus += 4.0
            if "điều 35" in haystack or (
                "người lao động có quyền đơn phương chấm dứt hợp đồng lao động" in haystack
                and "không cần báo trước" in haystack
            ):
                bonus += 9.0
            if "không được trả đủ lương" in haystack or "trả lương không đúng thời hạn" in haystack:
                bonus += 5.0
            if "không được bố trí theo đúng công việc" in haystack or "địa điểm làm việc" in haystack:
                bonus += 4.0
            if "điều 40" in haystack or "nửa tháng tiền lương" in haystack:
                bonus += 5.0
            if "điều 48" in haystack or "xác nhận thời gian đóng bảo hiểm xã hội" in haystack:
                bonus += 6.0
            if "điều 97" in haystack or ("không được chậm quá 30 ngày" in haystack and "trả thêm" in haystack):
                bonus += 4.0
            if "người sử dụng lao động phải báo trước cho người lao động" in haystack and "điều 35" not in haystack:
                bonus -= 5.0
            if any(
                term in haystack
                for term in [
                    "đình công",
                    "trợ cấp thất nghiệp",
                    "mức đóng bảo hiểm thất nghiệp",
                    "tiền lương ngừng việc",
                    "tạm ứng tiền lương",
                    "người cai thầu",
                ]
            ):
                bonus -= 5.0

        is_land_transfer_query = any(
            term in lowered_query
            for term in [
                "đất",
                "quyền sử dụng đất",
                "sổ đỏ",
                "sổ hồng",
                "sang tên",
                "chuyển nhượng",
            ]
        )
        if is_land_transfer_query:
            if "luật đất đai" in haystack:
                bonus += 3.0
            if any(term in haystack for term in ["đăng ký biến động", "sang tên", "chuyển nhượng quyền sử dụng đất"]):
                bonus += 4.0
            if any(term in haystack for term in ["lệ phí trước bạ", "thuế thu nhập cá nhân"]):
                bonus += 2.0
            if any(
                term in haystack
                for term in [
                    "quy hoạch sử dụng đất",
                    "đấu giá quyền sử dụng đất",
                    "đất công",
                    "giao đất không thông qua đấu giá",
                ]
            ) and not any(
                term in lowered_query
                for term in ["quy hoạch", "đấu giá", "đất công", "thu hồi đất", "bồi thường giải phóng mặt bằng"]
            ):
                bonus -= 6.0

        return bonus

    @staticmethod
    def _diversify(
        references: list[SourceReference],
        limit: int,
        max_per_document: int = 2,
    ) -> list[SourceReference]:
        selected: list[SourceReference] = []
        per_document_count: dict[int, int] = {}
        for reference in references:
            count = per_document_count.get(reference.document_id, 0)
            if count >= max_per_document:
                continue
            selected.append(reference)
            per_document_count[reference.document_id] = count + 1
            if len(selected) == limit:
                return selected

        selected_ids = {reference.chunk_id for reference in selected}
        for reference in references:
            if reference.chunk_id in selected_ids:
                continue
            selected.append(reference)
            if len(selected) == limit:
                break
        return selected
