"""Document management router — upload, search, and manage documents.

This router proxies requests to the verity-rag server and augments
responses with additional status information.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from mysterium.config import Settings, get_settings
from mysterium.clients.rag_client import RAGClient

router = APIRouter(prefix="/api/documents", tags=["documents"])


async def get_rag_client(settings: Settings = Depends(get_settings)) -> RAGClient:
    """Dependency providing a connected RAG client."""
    return RAGClient(base_url=settings.rag_server_url)


@router.get("/health")
async def health_check(
    rag: RAGClient = Depends(get_rag_client),
):
    """Check verity-rag server health."""
    try:
        status = await rag.health()
        return {"status": "ok", "rag_server": status}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"RAG server unreachable: {e}")


# ── Collections ─────────────────────────────────────────────────────


@router.get("/collections")
async def list_collections(
    rag: RAGClient = Depends(get_rag_client),
):
    """List all collections in the RAG system."""
    collections = await rag.list_collections()
    return {
        "items": [
            {
                "name": c.name,
                "total_vectors": c.total_vectors,
                "dim": c.dim,
                "indexing_status": c.indexing_status,
            }
            for c in collections
        ],
        "total": len(collections),
    }


@router.post("/collections")
async def create_collection(
    name: str = Query(..., min_length=1, max_length=64),
    rag: RAGClient = Depends(get_rag_client),
):
    """Create a new collection."""
    message = await rag.create_collection(name)
    return {"message": message}


@router.delete("/collections/{name}")
async def delete_collection(
    name: str,
    rag: RAGClient = Depends(get_rag_client),
):
    """Delete a collection."""
    message = await rag.delete_collection(name)
    return {"message": message}


# ── Documents ───────────────────────────────────────────────────────


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str = Form("documents"),
    rag: RAGClient = Depends(get_rag_client),
):
    """Upload a document for RAG ingestion.

    Supported formats: .txt, .md, .docx, .pdf
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Validate extension
    allowed = {".txt", ".md", ".docx", ".pdf"}
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if f".{ext}" not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{ext}. Allowed: {sorted(allowed)}",
        )

    content = await file.read()
    result = await rag.upload_document(
        content,
        filename=file.filename,
        collection_name=collection_name,
    )
    return result


@router.get("")
async def list_documents(
    collection_name: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    rag: RAGClient = Depends(get_rag_client),
):
    """List tracked documents."""
    items, total = await rag.list_documents(
        collection_name=collection_name,
        status=status,
        page=page,
        per_page=per_page,
    )
    return {
        "items": [
            {
                "id": d.id,
                "collection_name": d.collection_name,
                "filename": d.filename,
                "filesize": d.filesize,
                "filetype": d.filetype,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "error_message": d.error_message,
                "created_at": d.created_at,
                "completed_at": d.completed_at,
            }
            for d in items
        ],
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{doc_id}")
async def get_document(
    doc_id: str,
    rag: RAGClient = Depends(get_rag_client),
):
    """Get document details."""
    doc = await rag.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: str,
    rag: RAGClient = Depends(get_rag_client),
):
    """Delete a document."""
    deleted = await rag.delete_document(doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted"}


# ── Search ──────────────────────────────────────────────────────────


class SearchQuery(BaseModel):
    """Search request parameters passed as JSON body."""

    query: str = Field(..., min_length=1)
    collection_name: str = "documents"
    limit: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    use_reranker: bool = False


@router.post("/search")
async def search_documents(
    body: SearchQuery,
    rag: RAGClient = Depends(get_rag_client),
):
    """Search documents in a collection."""
    results = await rag.search(
        query=body.query,
        collection_name=body.collection_name,
        limit=body.limit,
        min_score=body.min_score,
        use_reranker=body.use_reranker,
    )
    return {
        "results": [
            {
                "content": r.content,
                "score": r.score,
                "metadata": r.metadata,
                "parent_doc_id": r.parent_doc_id,
            }
            for r in results
        ],
        "query": body.query,
        "collection_name": body.collection_name,
        "total": len(results),
    }
