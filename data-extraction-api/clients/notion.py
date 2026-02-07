"""
Notion API client for extracting raw data.
Uses Bearer token authentication with Notion-Version header.
"""

from typing import Any, Dict, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from utils.config import get_settings
from utils.exceptions import (
    InvalidTokenError,
    RateLimitError,
    TimeoutError,
    ExternalAPIError
)


class NotionClient:
    """Async HTTP client for Notion API."""
    
    BASE_URL = "https://api.notion.com"
    NOTION_VERSION = "2022-06-28"
    
    def __init__(self):
        settings = get_settings()
        self.database_id = settings.notion_database_id
        self.timeout = settings.request_timeout
        self.max_retries = settings.max_retries
        
        self.headers = {
            "Authorization": f"Bearer {settings.notion_token}",
            "Notion-Version": self.NOTION_VERSION,
            "Content-Type": "application/json"
        }
    
    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        """Handle HTTP response and raise appropriate exceptions."""
        if response.status_code == 401:
            raise InvalidTokenError("Invalid Notion integration token")
        elif response.status_code == 429:
            raise RateLimitError("Notion rate limit exceeded")
        elif response.status_code == 404:
            raise ExternalAPIError("Notion", "Resource not found", 404)
        elif response.status_code >= 400:
            raise ExternalAPIError(
                "Notion",
                f"Request failed with status {response.status_code}: {response.text}",
                response.status_code
            )
        return response.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError))
    )
    async def _request(
        self,
        method: str,
        endpoint: str,
        json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an HTTP request with retry logic."""
        url = f"{self.BASE_URL}{endpoint}"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json_body
                )
                return self._handle_response(response)
        except httpx.TimeoutException:
            raise TimeoutError(f"Notion request timed out after {self.timeout}s")
    
    async def query_database(self, page_size: int = 50) -> Dict[str, Any]:
        """
        Query the configured Notion database.
        
        Args:
            page_size: Number of results per page
            
        Returns:
            Raw Notion database query response
        """
        body = {
            "page_size": page_size
        }
        return await self._request(
            "POST",
            f"/v1/databases/{self.database_id}/query",
            json_body=body
        )
    
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Get a single Notion page.
        
        Args:
            page_id: Notion page ID
            
        Returns:
            Raw Notion page response
        """
        return await self._request("GET", f"/v1/pages/{page_id}")
