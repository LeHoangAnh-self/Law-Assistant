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
        scope: str | None = None,
        issuing_authority: str | None = None,
        external_docid: str | None = None,
        issued_date_from: str | None = None,
        issued_date_to: str | None = None,
        effective_date_from: str | None = None,
        effective_date_to: str | None = None,
        expired_date_from: str | None = None,
        expired_date_to: str | None = None,
    ) -> dict:
        params: dict[str, str | int] = {"query": query, "page": page, "size": size}
        optional_params = {
            "documentType": document_type,
            "validityStatus": validity_status,
            "scope": scope,
            "issuingAuthority": issuing_authority,
            "externalDocid": external_docid,
            "issuedDateFrom": issued_date_from,
            "issuedDateTo": issued_date_to,
            "effectiveDateFrom": effective_date_from,
            "effectiveDateTo": effective_date_to,
            "expiredDateFrom": expired_date_from,
            "expiredDateTo": expired_date_to,
        }
        params.update({key: value for key, value in optional_params.items() if value})
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
