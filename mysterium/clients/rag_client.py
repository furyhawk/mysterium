"""HTTP client for verity-rag API.

verity-rag is a self-hosted document ingestion and retrieval service.
This client wraps its REST API for document upload, search, and collection management.

API reference: https://pypi.org/project/verity-rag/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


@dataclass
class SearchResult:
    """A single search result from the RAG system."""

    content: str
    score: float
    metadata: dict[str, Any]
    parent_doc_id: str | None = None
    chunk_id: str | None = None


@dataclass
class DocumentItem:
    """A tracked document in list views."""

    id: str
    collection_name: str
    filename: str
    filesize: int
    filetype: str
    status: str
    chunk_count: int = 0
    source_path: str = ""
    error_message: str | None = None
    created_at: str = ""
    completed_at: str | None = None


@dataclass
class CollectionItem:
    """Collection metadata."""

    name: str
    total_vectors: int
    dim: int
    indexing_status: str = "complete"


class RAGClient:
    """Async HTTP client for the verity-rag API.

    Usage:
        client = RAGClient(base_url="http://localhost:8100")
        result = await client.upload_document("report.pdf")
        results = await client.search("quarterly earnings")
    """

    def __init__(self, base_url: str = "http://localhost:8100") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ── Health ──────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        """Check the RAG server health."""
        resp = await self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    # ── Collections ─────────────────────────────────────────────────

    async def list_collections(self) -> list[CollectionItem]:
        """List all available collections."""
        resp = await self._client.get("/api/v1/collections")
        resp.raise_for_status()
        data = resp.json()
        return [
            CollectionItem(
                name=item["name"],
                total_vectors=item.get("total_vectors", 0),
                dim=item.get("dim", 0),
                indexing_status=item.get("indexing_status", "complete"),
            )
            for item in data.get("items", [])
        ]

    async def create_collection(self, name: str) -> str:
        """Create a new collection."""
        resp = await self._client.post(f"/api/v1/collections?name={name}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", "")

    async def delete_collection(self, name: str) -> str:
        """Delete a collection and all its vectors."""
        resp = await self._client.delete(f"/api/v1/collections/{name}")
        resp.raise_for_status()
        data = resp.json()
        return data.get("message", "")

    async def get_collection(self, name: str) -> CollectionItem:
        """Get collection stats."""
        resp = await self._client.get(f"/api/v1/collections/{name}")
        resp.raise_for_status()
        data = resp.json()
        return CollectionItem(
            name=data["name"],
            total_vectors=data.get("total_vectors", 0),
            dim=data.get("dim", 0),
            indexing_status=data.get("indexing_status", "complete"),
        )

    # ── Documents ───────────────────────────────────────────────────

    async def upload_document(
        self,
        file_path: str | Path | bytes,
        *,
        filename: str | None = None,
        collection_name: str = "documents",
    ) -> dict[str, Any]:
        """Upload a document for ingestion.

        Args:
            file_path: Path to file or raw bytes.
            filename: Required when passing raw bytes. When file_path is a path,
                      the filename is inferred from the path.
            collection_name: Target collection.

        Returns:
            Upload response dict with id, filename, collection, status.
        """
        if isinstance(file_path, bytes):
            if not filename:
                msg = "filename is required when uploading raw bytes"
                raise ValueError(msg)
            files = {"file": (filename, file_path)}
        else:
            p = Path(file_path)
            files = {"file": (p.name, p.read_bytes())}

        resp = await self._client.post(
            "/api/v1/documents/upload",
            params={"collection_name": collection_name},
            files=files,
        )
        resp.raise_for_status()
        return resp.json()

    async def list_documents(
        self,
        collection_name: str | None = None,
        status: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[list[DocumentItem], int]:
        """List tracked documents with optional filters."""
        params: dict[str, str | int] = {"page": page, "per_page": per_page}
        if collection_name:
            params["collection_name"] = collection_name
        if status:
            params["status"] = status

        resp = await self._client.get("/api/v1/documents", params=params)
        resp.raise_for_status()
        data = resp.json()
        items = [
            DocumentItem(
                id=doc["id"],
                collection_name=doc.get("collection_name", ""),
                filename=doc["filename"],
                filesize=doc["filesize"],
                filetype=doc.get("filetype", ""),
                status=doc["status"],
                chunk_count=doc.get("chunk_count", 0),
                source_path=doc.get("source_path", ""),
                error_message=doc.get("error_message"),
                created_at=str(doc.get("created_at", "")),
                completed_at=str(doc["completed_at"]) if doc.get("completed_at") else None,
            )
            for doc in data.get("items", [])
        ]
        return items, data.get("total", 0)

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Get document details by ID."""
        resp = await self._client.get(f"/api/v1/documents/{doc_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document. Returns True if deleted."""
        resp = await self._client.delete(f"/api/v1/documents/{doc_id}")
        if resp.status_code == 404:
            return False
        resp.raise_for_status()
        return True

    # ── Search ──────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        collection_name: str = "documents",
        limit: int = 5,
        min_score: float = 0.0,
        use_reranker: bool = False,
    ) -> list[SearchResult]:
        """Search documents in a collection.

        Args:
            query: Natural language query.
            collection_name: Collection to search.
            limit: Max results (1-50).
            min_score: Minimum similarity score (0.0-1.0).
            use_reranker: Whether to apply cross-encoder reranking.

        Returns:
            List of search results sorted by relevance.
        """
        payload = {
            "query": query,
            "collection_name": collection_name,
            "limit": limit,
            "min_score": min_score,
            "use_reranker": use_reranker,
        }
        resp = await self._client.post("/api/v1/search", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return [
            SearchResult(
                content=item["content"],
                score=item["score"],
                metadata=item.get("metadata", {}),
                parent_doc_id=item.get("parent_doc_id"),
                chunk_id=item.get("chunk_id"),
            )
            for item in data.get("results", [])
        ]

    async def search_multi(
        self,
        query: str,
        collection_names: list[str],
        limit: int = 5,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Search across multiple collections."""
        payload = {
            "query": query,
            "collection_names": collection_names,
            "limit": limit,
            "min_score": min_score,
        }
        resp = await self._client.post("/api/v1/search/multi", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return [
            SearchResult(
                content=item["content"],
                score=item["score"],
                metadata=item.get("metadata", {}),
                parent_doc_id=item.get("parent_doc_id"),
                chunk_id=item.get("chunk_id"),
            )
            for item in data.get("results", [])
        ]
