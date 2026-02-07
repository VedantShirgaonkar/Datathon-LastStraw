"""
Notion extraction API endpoints.
"""

from typing import Any, Dict

from fastapi import APIRouter, Query

from clients.notion import NotionClient

router = APIRouter(prefix="/notion", tags=["Notion"])


@router.get(
    "/database/query",
    summary="Query Notion Database",
    description="Query the configured Notion database."
)
async def query_database(
    page_size: int = Query(default=50, ge=1, le=100, description="Number of results per page")
) -> Dict[str, Any]:
    """
    Query the configured Notion database.
    
    - **page_size**: Number of results per page (default: 50, max: 100)
    
    Returns raw Notion database query response.
    """
    client = NotionClient()
    return await client.query_database(page_size=page_size)


@router.get(
    "/page/{page_id}",
    summary="Get Notion Page",
    description="Get a single Notion page by ID."
)
async def get_page(page_id: str) -> Dict[str, Any]:
    """
    Get a single Notion page.
    
    - **page_id**: Notion page ID
    
    Returns raw Notion page response.
    """
    client = NotionClient()
    return await client.get_page(page_id=page_id)
