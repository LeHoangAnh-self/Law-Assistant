import httpx


class LlmClient:
    def __init__(
        self,
        provider: str,
        api_base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.provider = provider
        self.api_base_url = api_base_url
        self.api_key = api_key
        self.model = model

    async def generate(self, prompt: str) -> str:
        if self.provider == "stub":
            return (
                "LLM provider is not configured yet. Retrieved legal references are available, "
                "and this is the prompt that would be sent to the model:\n\n"
                f"{prompt}"
            )
        if self.provider == "openai-compatible":
            return await self._generate_openai_compatible(prompt)
        raise ValueError(f"Unsupported LLM provider: {self.provider}")

    async def _generate_openai_compatible(self, prompt: str) -> str:
        if not self.api_base_url or not self.api_key or not self.model:
            raise ValueError("OpenAI-compatible provider requires base URL, API key, and model")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
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
