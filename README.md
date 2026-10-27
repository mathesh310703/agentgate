# AgentGate

AgentGate is a plugin for browser agents that stops untrusted on-screen content (page text, images, popups, chat widgets) from commanding the agent: only the user's task may direct actions, and everything the agent reads from a page is treated as data. This repo holds the plugin work and its evaluation harness; the vision model under test is Muse Spark Open via Baseten's OpenAI-compatible Model API.

## Setup (Windows, NVIDIA GPU)

```bash
python -m venv .venv
.venv\Scripts\pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu126
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
copy .env.example .env      # then put your key after BASETEN_API_KEY= (never commit .env)
```

## Quick start

```bash
.venv\Scripts\python scripts/spark_smoke.py   # one text call + one screenshot call; prints latency, tokens, cost
.venv\Scripts\python -m agentlab.spend        # spend per stage from eval/cost_log.csv
.venv\Scripts\python tests/test_llm_budget.py # offline budget tests (no API calls)
```

Every real model call is logged to `eval/cost_log.csv`; responses are cached on disk so reruns cost nothing.

## Budgets and guards (agentlab/llm.py)

- Every call names a stage; budgets (USD): dev 5, baseline 15, defense 20, benchmark 30, arena 20, reserve 10. A call whose worst-case cost would exceed its stage budget is refused before sending.
- Total spend past $18 needs explicit confirmation (`AGENTGATE_CONFIRM_OVER_18=1`).
- `max_tokens` is capped at 2000, reasoning included; screenshots are sent as JPEG at most 768 px wide.
- Experiments use pilot mode (`agentlab/pilot.py`): 5 trials with cost and results printed; the full set only with `--full`.
