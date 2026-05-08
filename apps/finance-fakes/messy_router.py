"""
Messy finance router — deliberately exhibits the four failure modes from
ARCHITECTURE.md §1:

  1. Name collisions       — case/style variants of the same action
  2. Semantic duplicates   — different names, overlapping behavior
  3. Tool overloading      — same name, divergent schemas (modeled here as
                             three close-named operations with different
                             request shapes, since OpenAPI doesn't allow a
                             literal duplicate operationId)
  4. Ungrouped tools       — flat names with no domain prefix

This router is intentionally bad. Do NOT clean it up.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from store import CUSTOMERS, INVOICES, search_customers, list_invoices

router = APIRouter(prefix="/messy", tags=["messy"])


# --- shared response shapes (kept loose on purpose) ---

class CustomerOut(BaseModel):
    id: str
    name: str
    email: str
    tier: str


class GenericOk(BaseModel):
    ok: bool
    detail: str


# ============================================================
# 1. Name collisions — four ways to spell "create a customer"
# ============================================================

class CreateCustomerBody(BaseModel):
    name: str
    email: str
    tier: str = "bronze"


@router.post(
    "/createCustomer",
    operation_id="createCustomer",
    summary="[collision] Create customer (camelCase)",
    response_model=CustomerOut,
)
def createCustomer(body: CreateCustomerBody):
    new_id = f"c-{len(CUSTOMERS) + 1:03d}"
    rec = {"id": new_id, **body.model_dump()}
    CUSTOMERS[new_id] = rec
    return rec


@router.post(
    "/Create_Customer",
    operation_id="Create_Customer",
    summary="[collision] Create customer (PascalCase + underscore)",
    response_model=CustomerOut,
)
def Create_Customer(body: CreateCustomerBody):
    new_id = f"c-{len(CUSTOMERS) + 1:03d}"
    rec = {"id": new_id, **body.model_dump()}
    CUSTOMERS[new_id] = rec
    return rec


@router.post(
    "/customer_create",
    operation_id="customer_create",
    summary="[collision] Create customer (snake_case, no domain prefix)",
    response_model=CustomerOut,
)
def customer_create(body: CreateCustomerBody):
    new_id = f"c-{len(CUSTOMERS) + 1:03d}"
    rec = {"id": new_id, **body.model_dump()}
    CUSTOMERS[new_id] = rec
    return rec


@router.post(
    "/CustomerAPI_Final_v3",
    operation_id="CustomerAPI_Final_v3",
    summary="[collision] Create customer (legacy versioned name)",
    response_model=CustomerOut,
)
def CustomerAPI_Final_v3(body: CreateCustomerBody):
    new_id = f"c-{len(CUSTOMERS) + 1:03d}"
    rec = {"id": new_id, **body.model_dump()}
    CUSTOMERS[new_id] = rec
    return rec


# ============================================================
# 2. Semantic duplicates — three ways to "find a customer"
# ============================================================

@router.get(
    "/customer_find",
    operation_id="customer_find",
    summary="[semantic-dup] Find customers matching a term",
    response_model=list[CustomerOut],
)
def customer_find(q: str = Query("", description="search term")):
    return search_customers(q)


@router.get(
    "/customer_search",
    operation_id="customer_search",
    summary="[semantic-dup] Search the customer list",
    response_model=list[CustomerOut],
)
def customer_search(query: str = Query("", description="search term")):
    return search_customers(query)


@router.get(
    "/customer_lookup",
    operation_id="customer_lookup",
    summary="[semantic-dup] Look up a customer by partial match",
    response_model=list[CustomerOut],
)
def customer_lookup(term: str = Query("", description="search term")):
    return search_customers(term)


# ============================================================
# 3. Tool overloading — three "invoice_create" with divergent schemas
# (OpenAPI/FastAPI won't allow literal duplicate operationIds, so we
# expose three close-named variants — the resolver should still cluster.)
# ============================================================

class InvoiceCreateV1(BaseModel):
    """Old schema: customer_id + amount only."""
    customer_id: str
    amount: float


class InvoiceCreateV2(BaseModel):
    """New schema: adds currency + due_date."""
    customer_id: str
    amount: float
    currency: str = "USD"
    due_date: Optional[str] = None


class InvoiceCreateLegacy(BaseModel):
    """Legacy schema: cust + total fields, different keys entirely."""
    cust: str = Field(..., description="customer id (legacy field name)")
    total: float = Field(..., description="amount (legacy field name)")
    ccy: str = Field("USD", description="currency (legacy field name)")


@router.post(
    "/invoice_create_v1",
    operation_id="invoice_create_v1",
    summary="[overload] Create invoice (v1 schema)",
)
def invoice_create_v1(body: InvoiceCreateV1):
    new_id = f"inv-{1000 + len(INVOICES) + 1}"
    rec = {"id": new_id, **body.model_dump(), "currency": "USD", "status": "open"}
    INVOICES[new_id] = rec
    return rec


@router.post(
    "/invoice_create_v2",
    operation_id="invoice_create_v2",
    summary="[overload] Create invoice (v2 schema)",
)
def invoice_create_v2(body: InvoiceCreateV2):
    new_id = f"inv-{1000 + len(INVOICES) + 1}"
    rec = {"id": new_id, **body.model_dump(), "status": "open"}
    INVOICES[new_id] = rec
    return rec


@router.post(
    "/invoice_create_legacy",
    operation_id="invoice_create_legacy",
    summary="[overload] Create invoice (legacy field names)",
)
def invoice_create_legacy(body: InvoiceCreateLegacy):
    new_id = f"inv-{1000 + len(INVOICES) + 1}"
    rec = {
        "id": new_id,
        "customer_id": body.cust,
        "amount": body.total,
        "currency": body.ccy,
        "status": "open",
    }
    INVOICES[new_id] = rec
    return rec


# ============================================================
# 4. Ungrouped tools — flat names, no domain prefix
# ============================================================

@router.get(
    "/lookup",
    operation_id="lookup",
    summary="[ungrouped] Generic lookup",
    response_model=list[CustomerOut],
)
def lookup(q: str = Query("", description="search term")):
    return search_customers(q)


@router.post(
    "/create",
    operation_id="create",
    summary="[ungrouped] Generic create (does customer create)",
    response_model=CustomerOut,
)
def create(body: CreateCustomerBody):
    new_id = f"c-{len(CUSTOMERS) + 1:03d}"
    rec = {"id": new_id, **body.model_dump()}
    CUSTOMERS[new_id] = rec
    return rec


@router.get(
    "/list",
    operation_id="list",
    summary="[ungrouped] Generic list (returns invoices)",
)
def list_(customer_id: Optional[str] = None, status: Optional[str] = None):
    return list_invoices(customer_id, status)
