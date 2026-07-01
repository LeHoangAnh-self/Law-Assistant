from rag_service.embedding import EmbeddingModel


def test_embedding_model_keeps_device_and_batch_size_config() -> None:
    model = EmbeddingModel("example-model", device="cpu", batch_size=7, local_files_only=True)

    assert model.model_name == "example-model"
    assert model.device == "cpu"
    assert model.batch_size == 7
    assert model.local_files_only is True


def test_default_embedding_model_is_vietlegal_harrier() -> None:
    from rag_service.config import Settings

    settings = Settings(_env_file=None)

    assert settings.embedding_model_name == "mainguyen9/vietlegal-harrier-0.6b"
    assert settings.embedding_dimension == 1024
    assert settings.embedding_query_instruction.startswith("Instruct:")
    assert settings.reranker_model_name == "Qwen/Qwen3-Reranker-0.6B"
    assert settings.llm_model == "luanngo/Qwen3-4B-VietNamese-Legal-Chat"
    assert settings.qdrant_delete_existing_chunks is True
    assert settings.chunk_size == 1500
    assert settings.chunk_overlap == 200
