# Eval Summary

- Deployment: `gpt-4o-mini`
- Prompts: 20, runs/prompt: 3, max turns/run: 3
- Total invocations per config: 60
- Scoring: a run is **correct** if the expected tool appears in *any* turn (multi-turn agent loop with synthetic tool results between turns).

## Correct-tool rate

| Config | Correct | Total | Rate |
|---|---|---|---|
| `A_messy` | 35 | 60 | **58.3%** |
| `B_governed` | 60 | 60 | **100.0%** |

**Absolute lift (governed − messy): +41.7 percentage points**

## Per-prompt detail

| Prompt | Expected | A_messy | B_governed |
|---|---|---|---|
| `cust-get-01` | `financeCustomerGet` | 3/3 | 3/3 |
| `cust-get-02` | `financeCustomerGet` | 3/3 | 3/3 |
| `cust-get-03` | `financeCustomerGet` | 2/3 | 3/3 |
| `cust-get-04` | `financeCustomerGet` | 3/3 | 3/3 |
| `cust-search-01` | `financeCustomerSearch` | 3/3 | 3/3 |
| `cust-search-02` | `financeCustomerSearch` | 3/3 | 3/3 |
| `cust-search-03` | `financeCustomerSearch` | 3/3 | 3/3 |
| `cust-search-04` | `financeCustomerSearch` | 3/3 | 3/3 |
| `inv-get-01` | `financeInvoiceGet` | 0/3 | 3/3 |
| `inv-get-02` | `financeInvoiceGet` | 0/3 | 3/3 |
| `inv-get-03` | `financeInvoiceGet` | 0/3 | 3/3 |
| `inv-get-04` | `financeInvoiceGet` | 0/3 | 3/3 |
| `inv-list-01` | `financeInvoiceList` | 3/3 | 3/3 |
| `inv-list-02` | `financeInvoiceList` | 3/3 | 3/3 |
| `inv-list-03` | `financeInvoiceList` | 3/3 | 3/3 |
| `inv-list-04` | `financeInvoiceList` | 3/3 | 3/3 |
| `quote-get-01` | `financeQuoteGet` | 0/3 | 3/3 |
| `quote-get-02` | `financeQuoteGet` | 0/3 | 3/3 |
| `quote-get-03` | `financeQuoteGet` | 0/3 | 3/3 |
| `quote-get-04` | `financeQuoteGet` | 0/3 | 3/3 |
