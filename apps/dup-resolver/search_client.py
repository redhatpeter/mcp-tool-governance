"""Azure AI Search index client — provision, upsert, vector query."""
from __future__ import annotations

from functools import lru_cache
from typing import Iterable

from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    SearchableField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

import config


@lru_cache(maxsize=1)
def _index_client() -> SearchIndexClient:
    return SearchIndexClient(endpoint=config.SEARCH_ENDPOINT, credential=config.search_credential())


@lru_cache(maxsize=1)
def _search_client() -> SearchClient:
    return SearchClient(
        endpoint=config.SEARCH_ENDPOINT,
        index_name=config.SEARCH_INDEX,
        credential=config.search_credential(),
    )


# ---------------------------------------------------------------------------
# Provision
# ---------------------------------------------------------------------------

INDEX_FIELDS = lambda: [  # noqa: E731 — lazy so EMBEDDING_DIMS is read at call time
    SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
    SimpleField(name="server", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SearchableField(name="tool_name", type=SearchFieldDataType.String, filterable=True),
    SearchableField(name="description", type=SearchFieldDataType.String),
    SearchableField(name="fingerprint_text", type=SearchFieldDataType.String),
    SimpleField(name="domain", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SimpleField(name="action", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SimpleField(name="entity", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="cluster_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
    SimpleField(name="canonical_id", type=SearchFieldDataType.String, filterable=True),
    SimpleField(name="is_canonical", type=SearchFieldDataType.Boolean, filterable=True),
    SimpleField(name="last_seen_utc", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
    SearchField(
        name="embedding",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        searchable=True,
        vector_search_dimensions=config.EMBEDDING_DIMS,
        vector_search_profile_name="hnsw-cosine",
    ),
]


def ensure_index() -> str:
    """Create the index if missing; return 'created' or 'exists'."""
    ic = _index_client()
    try:
        ic.get_index(config.SEARCH_INDEX)
        return "exists"
    except Exception:
        pass

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="hnsw-default",
                parameters=HnswParameters(metric="cosine", m=4, ef_construction=400, ef_search=500),
            )
        ],
        profiles=[
            VectorSearchProfile(name="hnsw-cosine", algorithm_configuration_name="hnsw-default")
        ],
    )

    index = SearchIndex(
        name=config.SEARCH_INDEX,
        fields=INDEX_FIELDS(),
        vector_search=vector_search,
    )
    ic.create_index(index)
    return "created"


def drop_index() -> None:
    try:
        _index_client().delete_index(config.SEARCH_INDEX)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Data plane
# ---------------------------------------------------------------------------

def upsert_documents(docs: list[dict]) -> int:
    """Upload-or-merge a list of docs. Returns count succeeded."""
    if not docs:
        return 0
    sc = _search_client()
    result = sc.merge_or_upload_documents(documents=docs)
    return sum(1 for r in result if r.succeeded)


def delete_documents(ids: list[str]) -> int:
    """Delete docs by primary key. Returns count succeeded."""
    if not ids:
        return 0
    sc = _search_client()
    result = sc.delete_documents(documents=[{"id": i} for i in ids])
    return sum(1 for r in result if r.succeeded)


def count_documents() -> int:
    sc = _search_client()
    return sc.get_document_count()


def all_documents(select: list[str] | None = None) -> list[dict]:
    """Page through every doc in the index. PoC scale ≤ 100 docs, so simple."""
    sc = _search_client()
    iterator = sc.search(search_text="*", select=select, top=1000)
    return [dict(d) for d in iterator]


def vector_query(vector: list[float], k: int = 5,
                 select: list[str] | None = None) -> list[dict]:
    """Return top-k nearest neighbors with their cosine similarity score
    (Azure AI Search returns `@search.score` which for HNSW + cosine is the
    rescaled similarity in [0,1] — close to 1 means similar).
    """
    sc = _search_client()
    vq = VectorizedQuery(vector=vector, k_nearest_neighbors=k, fields="embedding")
    iterator = sc.search(search_text=None, vector_queries=[vq], select=select, top=k)
    out: list[dict] = []
    for d in iterator:
        row = dict(d)
        row["_score"] = d.get("@search.score", 0.0) if isinstance(d, dict) else getattr(d, "@search.score", 0.0)
        out.append(row)
    return out
