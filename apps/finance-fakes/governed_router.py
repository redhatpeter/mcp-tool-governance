"""
Governed finance router — clean naming following `domain_entity_action`.

Per ARCHITECTURE.md §3, this router exposes 5–8 properly-named operations
that follow the naming standard from §9. APIM imports this router's OpenAPI,
turns it into an MCP server, and that becomes the GOVERNED surface.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from store import CUSTOMERS, INVOICES, now_iso, search_customers, list_invoices

router = APIRouter(prefix="/governed", tags=["governed"])


# --- schemas ---

class Customer(BaseModel):
    id: str
    name: str
    email: str
    tier: str


class CreateCustomerRequest(BaseModel):
    name: str = Field(..., examples=["Acme Corp"])
    email: str = Field(..., examples=["ap@acme.example"])
    tier: str = Field("bronze", examples=["bronze", "silver", "gold"])


class Invoice(BaseModel):
    id: str
    customer_id: str
    amount: float
    currency: str
    status: str


class CreateInvoiceRequest(BaseModel):
    customer_id: str
    amount: float
    currency: str = "USD"


class PaymentApproval(BaseModel):
    invoice_id: str
    approved: bool
    approver: str
    timestamp: str


class Quote(BaseModel):
    symbol: str
    price: float
    currency: str
    timestamp: str


# --- operations ---

@router.get(
    "/customers/{customer_id}",
    operation_id="finance_customer_get",
    summary="Get a customer by ID",
    response_model=Customer,
)
def finance_customer_get(customer_id: str):
    c = CUSTOMERS.get(customer_id)
    if not c:
        raise HTTPException(404, "customer not found")
    return c


@router.post(
    "/customers",
    operation_id="finance_customer_create",
    summary="Create a customer",
    response_model=Customer,
)
def finance_customer_create(body: CreateCustomerRequest):
    new_id = f"c-{len(CUSTOMERS) + 1:03d}"
    rec = {"id": new_id, **body.model_dump()}
    CUSTOMERS[new_id] = rec
    return rec


@router.get(
    "/customers",
    operation_id="finance_customer_search",
    summary="Search customers by name or email",
    response_model=list[Customer],
)
def finance_customer_search(q: str = Query("", description="search term")):
    return search_customers(q)


@router.get(
    "/invoices/{invoice_id}",
    operation_id="finance_invoice_get",
    summary="Get an invoice by ID",
    response_model=Invoice,
)
def finance_invoice_get(invoice_id: str):
    inv = INVOICES.get(invoice_id)
    if not inv:
        raise HTTPException(404, "invoice not found")
    return inv


@router.post(
    "/invoices",
    operation_id="finance_invoice_create",
    summary="Create an invoice",
    response_model=Invoice,
)
def finance_invoice_create(body: CreateInvoiceRequest):
    new_id = f"inv-{1000 + len(INVOICES) + 1}"
    rec = {"id": new_id, **body.model_dump(), "status": "open"}
    INVOICES[new_id] = rec
    return rec


@router.get(
    "/invoices",
    operation_id="finance_invoice_list",
    summary="List invoices, optionally filtered by customer or status",
    response_model=list[Invoice],
)
def finance_invoice_list(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
):
    return list_invoices(customer_id, status)


@router.post(
    "/payments/approve",
    operation_id="finance_payment_approve",
    summary="Approve payment of an invoice",
    response_model=PaymentApproval,
)
def finance_payment_approve(invoice_id: str, approver: str):
    if invoice_id not in INVOICES:
        raise HTTPException(404, "invoice not found")
    INVOICES[invoice_id]["status"] = "approved"
    return {
        "invoice_id": invoice_id,
        "approved": True,
        "approver": approver,
        "timestamp": now_iso(),
    }


@router.get(
    "/quotes/{symbol}",
    operation_id="finance_quote_get",
    summary="Get a market quote for a symbol",
    response_model=Quote,
)
def finance_quote_get(symbol: str):
    # Deterministic fake: hash symbol to a price.
    price = round(50 + (sum(ord(c) for c in symbol.upper()) % 500), 2)
    return {
        "symbol": symbol.upper(),
        "price": price,
        "currency": "USD",
        "timestamp": now_iso(),
    }
