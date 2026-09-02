"""Elasticsearch global search with tenant and permission filters."""

from typing import Any

from elasticsearch import AsyncElasticsearch

from app.core.config import get_settings

settings = get_settings()

SEARCH_INDICES = [
    "shipments",
    "customers",
    "vendors",
    "carriers",
    "rates",
    "invoices",
    "documents",
]

INDEX_MAPPINGS: dict[str, dict[str, Any]] = {
    name: {
        "mappings": {
            "properties": {
                "tenant_id": {"type": "keyword"},
                "entity_id": {"type": "keyword"},
                "title": {"type": "text"},
                "summary": {"type": "text"},
                "status": {"type": "keyword"},
                "search_text": {"type": "text"},
            }
        }
    }
    for name in SEARCH_INDICES
}


class SearchService:
    def __init__(self) -> None:
        self._client: AsyncElasticsearch | None = None
        self.available = False

    async def connect(self) -> None:
        self._client = AsyncElasticsearch(settings.elasticsearch_url)

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    @property
    def client(self) -> AsyncElasticsearch:
        if not self._client:
            raise RuntimeError("Elasticsearch not connected")
        return self._client

    async def ensure_indices(self) -> None:
        for index, body in INDEX_MAPPINGS.items():
            if not await self.client.indices.exists(index=index):
                await self.client.indices.create(index=index, body=body)
        self.available = True

    def mark_unavailable(self) -> None:
        self.available = False

    async def search(
        self,
        *,
        query: str,
        tenant_id: str,
        allowed_indices: list[str],
        size: int = 20,
    ) -> dict[str, Any]:
        indices = [i for i in allowed_indices if i in SEARCH_INDICES] or SEARCH_INDICES
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"multi_match": {"query": query, "fields": ["title", "summary", "search_text"]}},
                    ],
                    "filter": [{"term": {"tenant_id": tenant_id}}],
                }
            },
            "size": size,
        }
        result = await self.client.search(index=",".join(indices), body=body)
        hits = [
            {
                "index": hit["_index"],
                "entity_id": hit["_source"].get("entity_id"),
                "title": hit["_source"].get("title"),
                "summary": hit["_source"].get("summary"),
                "score": hit["_score"],
            }
            for hit in result["hits"]["hits"]
        ]
        return {"data": hits, "meta": {"total": result["hits"]["total"]["value"]}, "errors": []}


search_service = SearchService()
