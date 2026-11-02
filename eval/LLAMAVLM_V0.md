# Llama 3.2 11B Vision as a victim model: not run (Nov 2, 2026)

**Result: nothing was measured.** The weights could not be downloaded, and the published licence terms appear to exclude the project owner. There are no leak, completion or false-block numbers, so tag `llama-victim-v0` was not created.

## Why it stopped

1. **Access: HTTP 403.** The Hugging Face account behind the `HF_TOKEN` in `.env` is not authorised for this repo:
   > Access to model meta-llama/Llama-3.2-11B-Vision-Instruct is restricted and you are not in the authorized list.

   The repo uses manual gating. The token itself works: the same request for `meta-llama/Llama-Prompt-Guard-2-22M` returns 200.
2. **Licence.** The terms on the model page say:
   > With respect to any multimodal models included in Llama 3.2, the rights granted under Section 1(a) of the Llama 3.2 Community License Agreement are not being granted to you if you are an individual domiciled in, or a company with a principal place of business in, the European Union.

   `docs/BUILD_RULES.md` lists the owner in Germany. This model is multimodal. Reading the terms is not legal advice, but as written they do not grant this entrant the rights to use the model.

## What was not done

- **No re-uploaded copy of the weights.** Community mirrors exist for many gated models. Using one would sidestep the gate and the licence.
- **No fit test.** Whether it fits 8 GB in 4-bit, and whether it can call the tools, is unknown. The safetensors total 21.3 GB (from the Hugging Face API); `bitsandbytes` is not installed, and was not installed for this.
- **No harness code.** It could not be tested without the weights.

## What would unblock it

The owner would need a licence basis for using this model, and then access to the repo. That decision is theirs. Qwen3-VL-2B (Apache-2.0) remains the local victim model: `eval/LOCALVLM_V1.md`, `eval/SET3_V0.md`.
