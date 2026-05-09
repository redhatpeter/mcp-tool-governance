"""Azure OpenAI embedding client.

Auth precedence:
1. ``AOAI_API_KEY`` env var (used by CI runners that don't have AAD/OIDC set up).
2. ``DefaultAzureCredential`` (local dev via ``az login``, or workload identity).
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable

from azure.identity import get_bearer_token_provider
from openai import AzureOpenAI

import config


@lru_cache(maxsize=1)
def _client() -> AzureOpenAI:
    api_key = os.getenv("AOAI_API_KEY")
    if api_key:
        return AzureOpenAI(
            azure_endpoint=config.AOAI_ENDPOINT,
            api_key=api_key,
            api_version=config.AOAI_API_VERSION,
        )
    token_provider = get_bearer_token_provider(
        config.credential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=config.AOAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version=config.AOAI_API_VERSION,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch-embed a list of strings. Returns list of vectors (3072 dims)."""
    if not texts:
        return []
    resp = _client().embeddings.create(
        model=config.AOAI_EMBEDDING_DEPLOYMENT,
        input=texts,
    )
    # OpenAI SDK returns objects with .embedding
    return [d.embedding for d in resp.data]


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]
