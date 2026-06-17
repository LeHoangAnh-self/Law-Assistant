from rag_service.config import get_settings
from rag_service.embedding import EmbeddingModel


def main() -> None:
    settings = get_settings()
    model = EmbeddingModel(
        settings.embedding_model_name,
        device=settings.embedding_device,
        batch_size=settings.embedding_batch_size,
        local_files_only=False,
    )
    vector = model.embed_one("Instruct: kiểm tra tải mô hình\nQuery: hiệu lực văn bản")
    print(f"Downloaded and loaded {settings.embedding_model_name}")
    print(f"Embedding dimension: {len(vector)}")


if __name__ == "__main__":
    main()
