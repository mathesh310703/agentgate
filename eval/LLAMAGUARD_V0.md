# Meta classifiers vs the provenance gate (Nov 2, 2026)

**Result: Llama Guard 3 1B was not measured.** This Hugging Face account has no access to the model (HTTP 403, below), so tag `llamaguard-v0` was not created. Prompt Guard 2 was re-measured on the actual planted image lines, which corrects an earlier number.

## The table

The units differ. A classifier scores a text; the gate checks a tool call. So the rows answer different questions, and the numbers are not directly comparable. Classifier rows use the fixed 0.5 threshold.

| defence | injected AgentDojo workspace | planted image lines (60 carriers) | false positives | source |
|---|---|---|---|---|
| Prompt Guard 2 22M, text flagged | **0/378** tool outputs (AUC 0.886, highest score 0.32) | **0/60** lines (AUC 0.787, highest score 0.0016) | 0/55 clean outputs, 0/60 clean OCR texts | `runs/llamaguard_v0/report.json` |
| Llama Guard 3 1B, text flagged | **not measured** (no access) | **not measured** | not measured | – |
| Provenance gate, scripted attack succeeds | 231/240 ungated → **0/240** replayable pairs | scripted obedient agent, gated: **0/60** | held-out half: 0 user calls blocked; asks on 28 attacked pairs and 2 of 20 clean tasks | `RESULTS.md` (a), `eval/READER_V0.md` |

What the gate row leaves out:
- It blocks by provenance on hand-picked policies, and it has its own holes: 5 adaptive gaps remain (`README.md`, Limits).
- Out of distribution it does much worse: with the frozen policy, travel stays at 116/120 (`RESULTS.md` (g)).
- Only 6 of 14 workspace injection goals are replayable.

## Correction to the earlier Prompt Guard image number

`eval/LAYER1.md` reports 0/60 on image carriers, scored on the **OCR text** of each image. OCR did not recover the planted address on 10 of those 60 images (`eval/READER_V0.md`), so at least those inputs did not hold the attack, and the number overstated what was tested.

Here the planted line itself is scored, whether or not OCR read it. The flag count stays at **0/60**, with a highest score of 0.0016.

**The AUC should not be read as detection.** It rises from 0.526 to 0.787, but positives are now one short line and negatives are whole documents' OCR text, so length differs between the classes. There are also only 16 distinct lines among the 60. No line comes near any usable threshold.

## Why Llama Guard was not measured

```
GET https://huggingface.co/meta-llama/Llama-Guard-3-1B/resolve/main/config.json -> 403, x-error-code: GatedRepo
Access to model meta-llama/Llama-Guard-3-1B is restricted and you are not in the authorized list.
```

- The repo uses manual gating, so access has to be requested by the account owner.
- No re-uploaded copy of the weights was used.
- This model is text only. The EU exclusion on the Llama 3.2 page names multimodal models, so it does not appear to apply here, but the owner should read the terms when requesting access.

`scripts/measure_llamaguard.py` runs the model automatically once access is granted: it classifies the same texts with one `generate` call each, and counts `unsafe` and categories. **That code path has never run against the real model**, so expect it may need a fix.

Llama Guard is a content-safety classifier with fixed hazard categories, and none of them is named prompt injection. That is a reason to expect few flags on these neutral texts. It is an expectation, not a measurement.

## Reproduce

```
.venv\Scripts\python scripts/measure_llamaguard.py --out runs/llamaguard_v0   # local, no API cost; needs HF_TOKEN in .env
```
