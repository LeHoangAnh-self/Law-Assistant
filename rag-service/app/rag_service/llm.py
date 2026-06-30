import httpx


class LlmClient:
    def __init__(
        self,
        provider: str,
        api_type: str = "chat_completions",
        api_base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_output_tokens: int = 4096,
    ) -> None:
        self.provider = provider
        self.api_type = api_type
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens

    async def generate(self, prompt: str) -> str:
        if self.provider == "stub":
            return (
                "LLM provider is not configured yet. Retrieved legal references are available, "
                "and this is the prompt that would be sent to the model:\n\n"
                f"{prompt}"
            )
        if self.provider == "openai-compatible":
            if self.api_type == "responses":
                return await self._generate_responses(prompt)
            return await self._generate_openai_compatible(prompt)
        raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def _generate_responses(self, prompt: str) -> str:
        if not self.api_base_url or not self.api_key or not self.model:
            raise ValueError("OpenAI Responses provider requires base URL, API key, and model")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict = {
            "model": self.model,
            "input": [{"role": "user", "content": prompt}],
            "max_output_tokens": self.max_output_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.api_base_url.rstrip('/')}/responses",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            output_text = data.get("output_text")
            if output_text:
                return output_text
            text_parts: list[str] = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") in {"output_text", "text"} and content.get("text"):
                        text_parts.append(content["text"])
            if text_parts:
                return "\n".join(text_parts)
            raise ValueError("Responses API returned no text output")

    async def _generate_openai_compatible(self, prompt: str) -> str:
        if not self.api_base_url or not self.api_key or not self.model:
            raise ValueError("OpenAI-compatible provider requires base URL, API key, and model")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": self.max_output_tokens,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
