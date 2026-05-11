# Demo Frontend (Streamlit)

A live, side-by-side UI that makes the value of the three governance layers visible
in under a minute.

## Panels

| Tab | What it shows |
|-----|---------------|
| 🎯 **Headline** | Pick a sample prompt → both servers run an agent in parallel → see which tool got picked, latency, ✅/❌ verdict, and a session-wide scoreboard. |
| 📋 **Catalog** | Live `tools/list` from each gateway. Counts collisions and missing descriptions; surfaces the `x-mcp-tools-filtered` header from L1's `tools-list-filter` policy. |
| 🔁 **L3 rewrite** | Three preset alias names → `tools/call` → see the `x-mcp-canonical-rewrite` header light up. |
| 🧠 **L2 sim** | Paste a tool description (as if from an incoming PR) → POSTs to the local dup-resolver `/similarity` → DUPLICATE / WARN / REVIEW / OK with the nearest match. |

## Run

```bash
cd frontend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 1) APIM master key — either env var or file at /tmp/apim-master-key.txt
#    (the rest of the repo already writes it there)
# export APIM_KEY=...

# 2) Optional: start the dup-resolver in another terminal so Tab 4 works
#    cd ../apps/dup-resolver && uvicorn main:app --port 8089

# 3) Make sure you're logged in for AOAI (DefaultAzureCredential)
#    az login

streamlit run app.py
```

Then open http://localhost:8501.

## Environment variables

| Var | Default |
|-----|---------|
| `APIM_BASE` | `https://apimopenai99.azure-api.net` |
| `APIM_KEY` | _(falls back to `APIM_KEY_FILE`)_ |
| `APIM_KEY_FILE` | `/tmp/apim-master-key.txt` |
| `AOAI_ENDPOINT` | `https://common-open-ai.openai.azure.com` |
| `AOAI_DEPLOYMENT` | `gpt-4o-mini` |
| `AOAI_API_VERSION` | `2024-10-21` |
| `RESOLVER_URL` | `http://127.0.0.1:8089` |
| `EVAL_MAX_TURNS` | `3` |

## Notes

- The agent loop is intentionally a near-clone of `eval/run_eval.py::run_one` so
  scoreboard numbers in the UI match what the offline evaluator produces.
- Sample prompts are loaded from `../eval/prompts.yaml`; the picker uses the
  `category`, `demo_priority`, and `narrator_note` fields from each entry.
- Tab 4 degrades gracefully — if the dup-resolver isn't running, the API call
  will surface the connection error in-page.
