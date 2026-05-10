# Draft Azure Support ticket — APIM-MCP body forwarding regression

**Status:** unsent (drafted 2026-05-10).
**Submit via:** Azure Portal → `apimopenai99` → Support + troubleshooting → New support request.

## Ticket metadata

| Field | Value |
| --- | --- |
| **Severity** | B (Moderate impact — feature degraded, no business outage) |
| **Service** | API Management |
| **Resource** | `/subscriptions/f5279601-4e81-4fe5-9b11-9d4ace3c40ca/resourceGroups/Default-ActivityLogAlerts/providers/Microsoft.ApiManagement/service/apimopenai99` |
| **Problem type** | Configuration and Setup → MCP server / AI gateway |
| **Title** | MCP server tools/call forwards only last argument value as backend body — regression of release-service-2026-03 fix |

## Body

```text
SUMMARY
On apimopenai99 (Developer SKU, stv2.1, eastus, releaseChannel=Preview),
MCP servers created from a managed REST API forward only ONE field's
raw scalar value as the backend HTTP request body on tools/call, instead
of constructing a JSON object from params.arguments.

This is a regression of the fix announced in release-service-2026-03
("Resolved issue where MCP POST request bodies were not forwarded to
backend APIs"). Prior reports (Microsoft Q&A 4371821, 5597117) showed
empty/zero-length bodies; we now see short scalar bodies whose value
matches the last property in params.arguments.

REPRODUCTION (no custom policies on the MCP server)

API: messy-mcp (MCP server exposing finance-api-messy-anti-pattern-reference)
Operation: Create_Customer  (POST /messy/Create_Customer)
Schema: { name:string, email:string, tier:string=bronze }, required: [name,email]

Call:
  POST https://apimopenai99.azure-api.net/messy-mcp/mcp
  Headers: Ocp-Apim-Subscription-Key, Content-Type: application/json,
           Accept: application/json, text/event-stream
  Body: { "jsonrpc":"2.0", "id":1, "method":"tools/call",
          "params": { "name":"createCustomer",
                      "arguments": { "name":"AAA", "email":"BBB", "tier":"CCC" } } }

Backend (verified via ngrok request inspector) receives:
  POST /messy/Create_Customer
  Content-Length: 3
  Body: CCC

Expected:
  Content-Length: 41
  Body: {"name":"AAA","email":"BBB","tier":"CCC"}

The backend correctly returns 422 json_invalid because "CCC" is not a
JSON object. Direct REST calls to the backend with proper JSON succeed.

INSTANCE DETAILS
- Subscription:    f5279601-4e81-4fe5-9b11-9d4ace3c40ca
- Resource group:  Default-ActivityLogAlerts
- APIM service:    apimopenai99
- SKU:             Developer
- platformVersion: stv2.1
- releaseChannel:  Preview
- Region:          eastus

PUBLIC TRACKING
GitHub issue: https://github.com/Azure-Samples/AI-Gateway/issues/315

QUESTIONS
1. Has the release-service-2026-03 MCP body-forwarding fix been deployed
   to apimopenai99? How can we verify the deployed gateway build version
   via ARM?
2. Is there a recommended workaround that does not depend on policy
   access to the unwrapped JSON-RPC envelope (which appears to be
   consumed upstream of both the MCP-server-scope and source-API-scope
   policy chains)?
3. Are v2 SKUs (Basicv2/Standardv2/Premiumv2) currently affected by the
   same scalar-body symptom, or only the original empty-body symptom?
```
