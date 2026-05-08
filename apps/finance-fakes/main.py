"""
finance-fakes — single FastAPI app exposing two routers:

  /governed/*   → clean naming (5–8 ops following domain_entity_action)
  /messy/*      → exhibits all four failure modes from ARCHITECTURE §1

Each router can be exported as its own OpenAPI doc via:

  GET /openapi-governed.json
  GET /openapi-messy.json

Those two JSONs are what APIM imports. APIM-MCP then exposes each as an
MCP server (one governed, one messy).
"""
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from governed_router import router as governed_router
from messy_router import router as messy_router

app = FastAPI(
    title="finance-fakes",
    version="0.1.0",
    description="PoC backend for MCP Tool Governance — fake finance data with two contrasting surfaces.",
)

app.include_router(governed_router)
app.include_router(messy_router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


def _filtered_openapi(prefix: str, title: str, server_url: str | None) -> dict:
    """Return an OpenAPI spec containing only routes under `prefix`."""
    full = get_openapi(
        title=title,
        version="0.1.0",
        description=f"finance-fakes — {prefix} surface",
        routes=app.routes,
    )
    filtered_paths = {p: v for p, v in full["paths"].items() if p.startswith(prefix)}
    full["paths"] = filtered_paths
    full["info"]["title"] = title
    if server_url:
        full["servers"] = [{"url": server_url}]
    return full


@app.get("/openapi-governed.json", tags=["meta"], include_in_schema=False)
def openapi_governed(server: str | None = None):
    return JSONResponse(_filtered_openapi("/governed", "finance-governed", server))


@app.get("/openapi-messy.json", tags=["meta"], include_in_schema=False)
def openapi_messy(server: str | None = None):
    return JSONResponse(_filtered_openapi("/messy", "finance-messy", server))
