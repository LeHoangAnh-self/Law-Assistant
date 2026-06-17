import httpx


class LawServiceClient:
    def __init__(self, base_url: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def search_documents(
        self,
        query: str,
        page: int = 0,
        size: int = 20,
        document_type: str | None = None,
        validity_status: str | None = None,
    ) -> dict:
        params: dict[str, str | int] = {"query": query, "page": page, "size": size}
        if document_type:
            params["documentType"] = document_type
        if validity_status:
            params["validityStatus"] = validity_status
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/documents", params=params)
            response.raise_for_status()
            return response.json()

    async def get_document_detail(self, document_id: int) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}/api/documents/{document_id}")
            response.raise_for_status()
            return response.json()

    def get_document_detail_sync(self, document_id: int) -> dict:
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/api/documents/{document_id}")
            response.raise_for_status()
            return response.json()
