import json

from rag_service.rabbit_bridge import publish_failed_message


class FakeChannel:
    def __init__(self) -> None:
        self.published: dict | None = None

    def basic_publish(self, **kwargs) -> None:
        self.published = kwargs


def test_publish_failed_message_makes_failure_observable() -> None:
    channel = FakeChannel()

    publish_failed_message(channel, "law.embedding.update.failed", "law.embedding.update", b"{bad")

    assert channel.published is not None
    assert channel.published["routing_key"] == "law.embedding.update.failed"
    assert channel.published["properties"].delivery_mode == 2
    payload = json.loads(channel.published["body"])
    assert payload["sourceQueue"] == "law.embedding.update"
    assert payload["body"] == "{bad"
