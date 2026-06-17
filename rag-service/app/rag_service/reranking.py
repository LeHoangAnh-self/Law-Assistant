from functools import cached_property

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
            return references[:limit]
        pairs = [(query, reference.text) for reference in references]
        scores = self._model.predict(pairs)
        rescored = [
            reference.model_copy(update={"score": float(score)})
            for reference, score in zip(references, scores, strict=True)
        ]
        return sorted(rescored, key=lambda reference: reference.score, reverse=True)[:limit]
