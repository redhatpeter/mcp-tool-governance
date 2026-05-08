#!/usr/bin/env python3
"""
Rewrite summary + description in finance-governed.json and finance-messy.json
so that APIM-MCP advertises tool names matching our canonical naming standard,
and so that the LLM gets rich when-to-use descriptions.

APIM-MCP derives the tool name from the OpenAPI `summary` field (camelCased).
We set summary = the EXACT desired tool name. If APIM strips underscores
on import, we will override per-tool in the Portal after recreation.

Also patches:
  - info.title / info.description (LLM/operator-facing)
  - per-parameter `description` for governed ops (LLM uses these to format args)

Run:  python3 _apply_naming.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

INFO = {
    "finance-governed.json": {
        "title": "Finance API (governed)",
        "description": (
            "Reference 'governed' finance API for the MCP Tool Governance PoC. "
            "Tools follow the {domain}_{entity}_{verb} naming standard, have "
            "single-purpose operations, and rich when-to-use / when-NOT-to-use "
            "descriptions designed for reliable LLM tool selection."
        ),
    },
    "finance-messy.json": {
        "title": "Finance API (messy — anti-pattern reference)",
        "description": (
            "Deliberately badly-designed finance API used as a NEGATIVE control "
            "for the MCP Tool Governance PoC. Demonstrates the four failure modes: "
            "name collisions, semantic duplicates, schema overloads, and ungrouped "
            "generic verbs. NOT FOR PRODUCTION USE."
        ),
    },
}

# operationId -> { paramName: description }
GOVERNED_PARAMS = {
    "finance_customer_get": {
        "customer_id": "Exact customer identifier, e.g. 'c-001'.",
    },
    "finance_customer_search": {
        "q": "Search query — partial match on customer name or email. Case-insensitive.",
    },
    "finance_invoice_get": {
        "invoice_id": "Exact invoice identifier, e.g. 'inv-1001'.",
    },
    "finance_invoice_list": {
        "customer_id": "Optional. Restrict results to invoices for a single customer (e.g. 'c-001').",
        "status": "Optional. Filter by invoice status. One of: 'draft', 'sent', 'paid', 'overdue'.",
    },
    "finance_payment_approve": {
        "invoice_id": "Identifier of the invoice to approve for payment.",
        "approver": "Identifier of the user or system authorizing the payment (e.g. an email or service principal name).",
    },
    "finance_quote_get": {
        "symbol": "Ticker symbol in uppercase, e.g. 'MSFT'.",
    },
}

# operationId -> (new summary == desired APIM tool name, new description)
GOVERNED = {
    "finance_customer_get": (
        "finance_customer_get",
        "Retrieve a single customer record by exact customer_id. "
        "USE WHEN you already know the customer_id. "
        "DO NOT USE for lookup by name/email — call finance_customer_search instead. "
        "Returns the full Customer object including contact fields."
    ),
    "finance_customer_create": (
        "finance_customer_create",
        "Create a new customer record. "
        "USE WHEN you have verified the customer does not already exist. "
        "DO NOT USE without first calling finance_customer_search to avoid duplicates. "
        "Required: name, email. Returns the new customer_id."
    ),
    "finance_customer_search": (
        "finance_customer_search",
        "Search customers by partial match on name or email. "
        "USE WHEN you need to find a customer by descriptive text, "
        "or BEFORE creating a new customer to check for duplicates. "
        "DO NOT USE for exact id lookup — use finance_customer_get instead. "
        "Returns up to 25 matches ranked by relevance."
    ),
    "finance_invoice_get": (
        "finance_invoice_get",
        "Retrieve a single invoice by exact invoice_id. "
        "USE WHEN you have a specific invoice_id and need its full detail "
        "(line items, status, amount, customer reference). "
        "DO NOT USE for browsing or filtering — use finance_invoice_list."
    ),
    "finance_invoice_create": (
        "finance_invoice_create",
        "Create a new invoice for an existing customer. "
        "USE WHEN the customer is already created/verified and you need to bill them. "
        "Required: customer_id, amount. Optional: currency (defaults to USD). "
        "DOES NOT send the invoice — only persists it in 'draft' status."
    ),
    "finance_invoice_list": (
        "finance_invoice_list",
        "List invoices with optional filters: customer_id (scope to one customer) "
        "and/or status (one of: draft, sent, paid, overdue). "
        "USE WHEN browsing or reporting. "
        "DO NOT USE when you already have a specific invoice_id — use finance_invoice_get. "
        "Returns a paginated list ordered by created_at desc."
    ),
    "finance_payment_approve": (
        "finance_payment_approve",
        "Approve payment release for an existing invoice. "
        "USE WHEN a human or upstream workflow has authorized payment. "
        "Required: invoice_id, approver. "
        "Idempotent: re-approving an already-approved invoice returns the existing approval. "
        "DOES NOT execute the payment — downstream payment-rails tool is responsible."
    ),
    "finance_quote_get": (
        "finance_quote_get",
        "Get the current market quote (bid/ask/last) for a ticker symbol. "
        "USE WHEN you need real-time pricing for a decision. "
        "Symbol format: uppercase ticker, e.g. MSFT. "
        "Quotes are advisory only — they are NOT execution prices and may be stale up to 250ms."
    ),
}

# For messy, we DELIBERATELY keep bad/colliding/overlapping NAMES so the demo
# can show what failure looks like. But we still write honest descriptions —
# part of the demo is showing that even good descriptions cannot save you
# when names collide or semantically overlap.
MESSY = {
    # --- collisions: 4 different operations all "create a customer" ---
    "createCustomer": (
        "createCustomer",
        "Create a customer. (camelCase variant — collides with three other "
        "customer-create tools on this server.)"
    ),
    "Create_Customer": (
        "Create_Customer",
        "Create a customer. (PascalCase + underscore variant — collides with "
        "three other customer-create tools on this server.)"
    ),
    "customer_create": (
        "customer_create",
        "Create a customer. (snake_case variant, no domain prefix — collides "
        "with three other customer-create tools on this server.)"
    ),
    "CustomerAPI_Final_v3": (
        "CustomerAPI_Final_v3",
        "Create a customer. (Legacy versioned name from a deprecated API — "
        "collides with three other customer-create tools on this server.)"
    ),

    # --- semantic duplicates: 3 search-customers tools with different param names ---
    "customer_find": (
        "customer_find",
        "Find customers matching a term. Parameter: q. "
        "(Semantic duplicate of customer_search and customer_lookup — "
        "the LLM cannot tell which to pick.)"
    ),
    "customer_search": (
        "customer_search",
        "Search the customer list. Parameter: query. "
        "(Semantic duplicate of customer_find and customer_lookup — "
        "same intent, different parameter name.)"
    ),
    "customer_lookup": (
        "customer_lookup",
        "Look up a customer by partial match. Parameter: term. "
        "(Semantic duplicate of customer_find and customer_search — "
        "same intent, different parameter name.)"
    ),

    # --- overloads: 3 invoice_create variants with incompatible schemas ---
    "invoice_create_v1": (
        "invoice_create_v1",
        "Create an invoice (v1 schema). Fields: customer_id, amount. "
        "(Overload variant — v1/v2/legacy share the name root but accept "
        "incompatible payloads.)"
    ),
    "invoice_create_v2": (
        "invoice_create_v2",
        "Create an invoice (v2 schema). Fields: customer_id, amount, currency, due_date. "
        "(Overload variant — v1/v2/legacy share the name root but accept "
        "incompatible payloads.)"
    ),
    "invoice_create_legacy": (
        "invoice_create_legacy",
        "Create an invoice (legacy schema). Fields: cust, total, ccy. "
        "(Overload variant with completely different field names than v1/v2.)"
    ),

    # --- ungrouped: generic verbs with no domain context ---
    "lookup": (
        "lookup",
        "Generic lookup. (Ungrouped — no domain prefix; the LLM has no way "
        "to know this is a customer lookup until it reads the response.)"
    ),
    "create": (
        "create",
        "Generic create — actually creates a customer. "
        "(Ungrouped — name gives no hint of the domain.)"
    ),
    "list": (
        "list",
        "Generic list — actually returns invoices. "
        "(Ungrouped — name gives no hint of the domain.)"
    ),
}


def apply(
    file_name: str,
    mapping: dict[str, tuple[str, str]],
    param_mapping: dict[str, dict[str, str]] | None = None,
) -> None:
    path = HERE / file_name
    doc = json.loads(path.read_text())

    # info
    info = INFO[file_name]
    doc["info"]["title"] = info["title"]
    doc["info"]["description"] = info["description"]

    seen = set()
    param_seen: set[tuple[str, str]] = set()
    for url, methods in doc["paths"].items():
        for method, op in methods.items():
            op_id = op.get("operationId")
            if op_id in mapping:
                new_summary, new_desc = mapping[op_id]
                op["summary"] = new_summary
                op["description"] = new_desc
                seen.add(op_id)
            if param_mapping and op_id in param_mapping:
                wanted = param_mapping[op_id]
                for p in op.get("parameters", []):
                    if p.get("name") in wanted:
                        p["description"] = wanted[p["name"]]
                        # Schema-level description too — some tools render that one
                        sch = p.get("schema")
                        if isinstance(sch, dict):
                            sch["description"] = wanted[p["name"]]
                        param_seen.add((op_id, p["name"]))

    missing = set(mapping) - seen
    if missing:
        raise SystemExit(f"{file_name}: operationIds in mapping but not in spec: {missing}")
    extra = {
        op.get("operationId")
        for methods in doc["paths"].values()
        for op in methods.values()
    } - set(mapping)
    if extra:
        raise SystemExit(f"{file_name}: operationIds in spec but not in mapping: {extra}")

    if param_mapping:
        wanted_pairs = {(op_id, name) for op_id, params in param_mapping.items() for name in params}
        missing_params = wanted_pairs - param_seen
        if missing_params:
            raise SystemExit(f"{file_name}: parameters in mapping but not in spec: {missing_params}")

    path.write_text(json.dumps(doc, indent=4) + "\n")
    print(f"  {file_name}: updated info + {len(seen)} operations + {len(param_seen)} parameters")


if __name__ == "__main__":
    print("Applying canonical names + rich descriptions...")
    apply("finance-governed.json", GOVERNED, GOVERNED_PARAMS)
    apply("finance-messy.json", MESSY)
    print("Done.")
