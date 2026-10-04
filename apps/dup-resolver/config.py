"""Centralized config + Azure credential factory."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load .env from the dup-resolver/ folder regardless of cwd
_BASE = Path(__file__).resolve().parent
load_dotenv(_BASE / ".env")


def _env(name: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"required env var {name} not set")
    return val or ""


# --- Azure OpenAI ---
AOAI_ENDPOINT = _env("AOAI_ENDPOINT", required=True)
AOAI_API_VERSION = _env("AOAI_API_VERSION", "2024-10-21")
AOAI_EMBEDDING_DEPLOYMENT = _env("AOAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# --- Azure AI Search ---
SEARCH_ENDPOINT = _env("SEARCH_ENDPOINT", required=True)
SEARCH_INDEX = _env("SEARCH_INDEX", "mcp-tool-fingerprints")
# Fallback for services that haven't enabled RBAC auth. Auth precedence:
# 1. SEARCH_ADMIN_KEY env var (preferred for CI — set as repo secret)
# 2. SEARCH_KEY_FILE pointing to a file containing the admin key (local dev)
# 3. DefaultAzureCredential (RBAC, when the service has it enabled)
SEARCH_ADMIN_KEY = _env("SEARCH_ADMIN_KEY", "")
SEARCH_KEY_FILE = _env("SEARCH_KEY_FILE", "")


def search_credential():
    """AzureKeyCredential if a key is available, otherwise AAD credential."""
    from azure.core.credentials import AzureKeyCredential
    if SEARCH_ADMIN_KEY:
        return AzureKeyCredential(SEARCH_ADMIN_KEY)
    if SEARCH_KEY_FILE:
        return AzureKeyCredential(Path(SEARCH_KEY_FILE).read_text().strip())
    return credential()

# --- APIM source of truth ---
APIM_GATEWAY_BASE = _env("APIM_GATEWAY_BASE", "https://apimopenai992.azure-api.net")
# Auth precedence: APIM_KEY env var > APIM_KEY_FILE path
APIM_KEY = _env("APIM_KEY", "")
APIM_KEY_FILE = _env("APIM_KEY_FILE", "/tmp/apim-master-key.txt")
MCP_SERVERS = [s.strip() for s in _env("MCP_SERVERS", "governed-mcp,messy-mcp").split(",") if s.strip()]

# --- Clustering / embeddings ---
EMBEDDING_DIMS = int(_env("EMBEDDING_DIMS", "3072"))
CLUSTER_THRESHOLD = float(_env("CLUSTER_THRESHOLD", "0.88"))
# Soft "reviewer should look at this" tier. Anything in
# [REVIEW_THRESHOLD, CLUSTER_THRESHOLD - 0.05) gets a REVIEW verdict in
# the PR comment but does NOT fail the check. Tuned from the
# precision/recall study (docs/eval/precision-recall.md): 0.65 catches
# real-world cross-vendor semantic duplicates (e.g. github.create_issue
# vs linear.createIssue at 0.651) without blocking on them.
REVIEW_THRESHOLD = float(_env("REVIEW_THRESHOLD", "0.65"))

# --- Canonical map (Cosmos) ---
# L2 elects a canonical per cluster and writes it here for L3 to read.
# Auth precedence mirrors the search client:
#   1. COSMOS_KEY env var (preferred for CI)
#   2. COSMOS_KEY_FILE pointing to a file with the master key
#   3. DefaultAzureCredential (RBAC, when the account allows AAD data-plane)
# If COSMOS_ENDPOINT is empty, the writer no-ops with a warning so
# the rest of ingest still runs (useful for early-stage local dev).
COSMOS_ENDPOINT = _env("COSMOS_ENDPOINT", "")
COSMOS_DATABASE = _env("COSMOS_DATABASE", "governance")
COSMOS_CONTAINER = _env("COSMOS_CONTAINER", "mcp-canonical-map")
COSMOS_KEY = _env("COSMOS_KEY", "")
COSMOS_KEY_FILE = _env("COSMOS_KEY_FILE", "")


def cosmos_key() -> str:
    if COSMOS_KEY:
        return COSMOS_KEY
    if COSMOS_KEY_FILE:
        return Path(COSMOS_KEY_FILE).read_text().strip()
    return ""


@lru_cache(maxsize=1)
def credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


def apim_subscription_key() -> str:
    if APIM_KEY:
        return APIM_KEY
    return Path(APIM_KEY_FILE).read_text().strip()
