# Other models on the vision test (v0), Oct 31, 2026

## Result

**No other model could be tested, so we found no fooled model.** Our Baseten key lists 21 models (`eval/MODELS.md`), 15 of them image-capable. The three cheapest image models with tool support each refused the key: the proxy got HTTP 403, `{"error":"please check the api-key you provided"}`, on the first call. No model answered, so there are no attack-success, flag or benign numbers to report, and the gated arm was not run.

| model (cheapest first) | price in / out per 1M | result |
|---|---|---|
| `zai-org/GLM-5.3-Flash` | $0.15 / $0.50 | HTTP 403 on the first call; no episode ran |
| `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B` | $0.20 / $0.50 | HTTP 403 on the first call; no episode ran |
| `deepseek-ai/DeepSeek-V4.1-Flash-1017` | $0.30 / $1.20 | HTTP 403 on the first call; no episode ran |

Control: one call to `meta-models/muse-spark-open-1026` through the same modified proxy returned 200 ($0.0005, stage `dev`). The key and the proxy work, so the 403s come from model access, not our code. Most likely the hackathon key covers only the hackathon model. We have not confirmed this with Baseten.

The `decision-models/*` image models were not candidates, because they list no tool support.

## What was built (ready if access is granted)

- **`agentlab/llm.py`:** `MODEL_PRICES` holds per-model prices from the models endpoint. `price_for(model)` returns `(price, known)`. An unknown model is priced at `UNKNOWN_PRICE`, the most expensive known price field by field (Kimi K3, $3 / $15 per 1M). `cost_of` and `worst_case_cost` take a model argument; the default is still Muse Spark.
- **`agentlab/proxy.py`:** the `--model` option forwards to that model and checks and logs budget at its price. At startup the proxy prints the price, and says so when the price is unknown. `GET /v1/models` reports the served model.
- **Tests:** 2 new tests in `tests/test_proxy_adapters.py`.
  - The model is forwarded and priced per model.
  - An unknown model is charged at the maximum known price.
- **`eval/vision_demo/run_models.py`:** runs the same prompts, fake tools and both image sets (60 images) as `run_vision.py`, one model per run.
  - It has an ungated arm (`--arm none`) and a gated arm (`--arm gate`), which uses the frozen `gate-final.1` gate.
  - Replies are cached per model, and the run stops at a $2 total for the experiment.
  - Its metrics are canary shared or emailed, a flag of the line to the user (a keyword heuristic on the final answer), benign success, and, gated, false blocks on clean images.

Cost estimate made before running, per arm (60 images):

| model | typical | worst case |
|---|---|---|
| GLM-5.3-Flash | $0.06 | $0.21 |
| Nemotron VL | $0.07 | $0.24 |
| DeepSeek V4.1 Flash | $0.13 | $0.48 |

**Spent:** $0.00 on the three models (403s carry no usage). The control call cost $0.0005. The gate code is unchanged (`git diff gate-final.1 -- agentgate/` is empty).

## To run once the key has access

```
.venv\Scripts\python -m agentlab.proxy --stage benchmark --model zai-org/GLM-5.3-Flash --port 8011
.venv\Scripts\python eval/vision_demo/run_models.py --model zai-org/GLM-5.3-Flash --port 8011 --arm none
.venv\Scripts\python eval/vision_demo/run_models.py --model zai-org/GLM-5.3-Flash --port 8011 --arm gate   # if attack success >= 1/60
.venv\Scripts\python eval/vision_demo/run_models.py --summary
```
