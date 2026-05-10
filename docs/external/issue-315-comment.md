# Draft comment to post on Azure-Samples/AI-Gateway#315

**Status:** unsent (drafted 2026-05-10).
**Target issue:** https://github.com/Azure-Samples/AI-Gateway/issues/315
**Submit with:**

```bash
gh issue comment 315 \
  --repo Azure-Samples/AI-Gateway \
  --body-file docs/external/issue-315-comment.md
```

(Strip everything above the `---` divider before submitting; only the
content below the divider is the comment body.)

---

### Update: confirmed regression of the original empty-body fix

After further triage, this is almost certainly a **regression of the
fix shipped in [release-service-2026-03][r1]** rather than an unrelated
bug. The release notes call out:

> Resolved issue where MCP POST request bodies were not forwarded to
> backend APIs, ensuring correct payload delivery during tool execution.

That fix replaced the prior "forward nothing" symptom (reported in
[Q&A 4371821][q1] Jul 2025 and [Q&A 5597117][q2] Oct 2025, both
documented as `Content-Length: 0` reaching the backend) with the
current "forward one scalar value" symptom we observe.

### Evidence the body is being assembled then partially overwritten

Same `tools/call`, same backend, three different argument sets:

| `arguments` sent                                                     | Backend `Content-Length` | Backend body |
| -------------------------------------------------------------------- | -----------------------: | ------------ |
| `{"name":"AAA","email":"BBB","tier":"CCC"}`                          | 3                        | `CCC`        |
| `{"name":"AAA","email":"BBB"}` (no `tier`)                           | 3                        | `BBB`        |
| `{}`                                                                 | 2                        | `{}`         |

The backend always receives the **last property's raw value**, not a
JSON object. Confirmed via ngrok request inspector with **all
custom policies stripped** from the MCP server (default `<base/>`
inbound only), so no user policy can be the cause.

### Why the documented community workarounds don't apply post-fix

1. The **`set-body` unwrap** workaround from [Q&A 4371821][q1]
   (`context.Request.Body.As<JObject>()["params"]["arguments"]`) at
   MCP-server scope returns 500 — APIM-MCP's JSON-RPC parser consumes
   the request stream **upstream** of the MCP-server policy chain, so
   the wrapped envelope is no longer visible at that scope.
2. The **preserve-and-replay** workaround from [Q&A 5597117][q2]
   (`Body.As<string>(preserveContent:true)` at the source-API operation
   scope) cannot recover the lost properties — by the time the request
   reaches the source operation, APIM-MCP has already collapsed the
   body to the single-scalar form.

### Confirmation requests

1. Can the team confirm whether the post-March-2026 codepath assembles
   the backend body by writing each property of `params.arguments`
   into a single buffer (last-write-wins), rather than constructing a
   JSON object?
2. Is there a way to query the deployed gateway build version of an
   APIM instance via ARM, so users can self-verify whether their
   instance has shipped a regression fix?
3. Has any v2-SKU customer been able to reproduce the scalar-body
   symptom, or does v2 only exhibit the original empty-body bug
   (matching Bruce Moe's [Dec 16 2025 reply][q1] that v2 had received
   the original fix at that time)?

[r1]: https://github.com/Azure/API-Management/releases/tag/release-service-2026-03
[q1]: https://learn.microsoft.com/en-us/answers/questions/4371821/
[q2]: https://learn.microsoft.com/en-us/answers/questions/5597117/
