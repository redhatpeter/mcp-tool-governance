"""In-memory fake finance data shared by both routers."""
from typing import Dict, List
from datetime import datetime, timezone

CUSTOMERS: Dict[str, dict] = {
    "c-001": {"id": "c-001", "name": "Acme Corp", "email": "ap@acme.example", "tier": "gold"},
    "c-002": {"id": "c-002", "name": "Globex Ltd", "email": "billing@globex.example", "tier": "silver"},
    "c-003": {"id": "c-003", "name": "Initech LLC", "email": "finance@initech.example", "tier": "bronze"},
}

INVOICES: Dict[str, dict] = {
    "inv-1001": {"id": "inv-1001", "customer_id": "c-001", "amount": 12500.00, "currency": "USD", "status": "open"},
    "inv-1002": {"id": "inv-1002", "customer_id": "c-002", "amount": 4200.50, "currency": "USD", "status": "paid"},
    "inv-1003": {"id": "inv-1003", "customer_id": "c-001", "amount": 875.00, "currency": "EUR", "status": "open"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def search_customers(q: str) -> List[dict]:
    q = (q or "").lower()
    return [c for c in CUSTOMERS.values() if q in c["name"].lower() or q in c["email"].lower()]


def list_invoices(customer_id: str | None = None, status: str | None = None) -> List[dict]:
    out = list(INVOICES.values())
    if customer_id:
        out = [i for i in out if i["customer_id"] == customer_id]
    if status:
        out = [i for i in out if i["status"] == status]
    return out
