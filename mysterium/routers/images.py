"""Image proxy router — serves document images extracted by the RAG server.

verity-rag extracts images from uploaded documents and serves their raw bytes
at ``GET /api/v1/images/{image_id}``. This router proxies that endpoint so the
frontend can render report and search images without cross-origin/auth issues.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from mysterium.clients.rag_client import RAGClient, RAGImageNotFoundError
from mysterium.config import Settings, get_settings

router = APIRouter(prefix="/api/images", tags=["images"])


async def get_rag_client(settings: Settings = Depends(get_settings)) -> RAGClient:
    """Dependency providing a connected RAG client."""
    return RAGClient(base_url=settings.rag_server_url)


@router.get("/{image_id}")
async def get_image(
    image_id: str,
    rag: RAGClient = Depends(get_rag_client),
) -> Response:
    """Proxy a document image from the RAG server as raw bytes.

    Returns the image bytes with the correct ``Content-Type`` so it renders
    directly in an ``<img src>`` tag.
    """
    try:
        data, mime_type = await rag.get_image(image_id)
    except RAGImageNotFoundError:
        raise HTTPException(status_code=404, detail="Image not found")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"RAG image server error: {e}")
    return Response(content=data, media_type=mime_type)
