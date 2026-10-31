# Models listed for our Baseten key

Source: `GET https://inference.baseten.co/v1/models` with our key, Oct 31, 2026 (read-only; no generation call was made for this list). Open weights: "yes" when the endpoint gives a Hugging Face id (that id is shown); "not stated" otherwise. Prices in USD per 1M tokens (input / output), from the endpoint.

**Listing is not access.** The endpoint lists 21 models, but a call to three of them through the proxy returned HTTP 403 "please check the api-key you provided" (see `eval/MODELS_V0.md`). Only `meta-models/muse-spark-open-1026` is known to accept our key.

| model id | name | open weights | images | tools | price in / out |
|---|---|---|---|---|---|
| `decision-models/baseten-joey-2b-latest` | joey-1 | not stated | yes | no | 0.01 / 0 |
| `decision-models/baseten-elephant-9b-latest` | elephant-1 | not stated | yes | no | 0.035 / 0 |
| `openai/gpt-oss-120b` | OpenAI GPT 120B | yes (known release; no HF id listed) | no | yes | 0.1 / 0.5 |
| `decision-models/baseten-mammoth-27b-latest` | mammoth-1 | not stated | yes | no | 0.1 / 0 |
| `deepseek-ai/DeepSeek-V4-Flash-0731` | DeepSeek V4 Flash 0731 | yes (`deepseek-ai/DeepSeek-V4-Flash-0731`) | no | yes | 0.13 / 0.26 |
| `zai-org/GLM-5.3-Flash` | GLM 5.3 Flash | yes (`zai-org/GLM-5.3-Flash`) | yes | yes | 0.15 / 0.5 |
| `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B` | Nemotron Super 3.5 | yes (`nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4`) | yes | yes | 0.2 / 0.5 |
| `deepseek-ai/DeepSeek-V4.1-Flash` | DeepSeek V4.1 Flash | yes (`deepseek-ai/DeepSeek-V4.1-Flash`) | yes | yes | 0.3 / 1.2 |
| `deepseek-ai/DeepSeek-V4.1-Flash-1017` | DeepSeek V4.1 Flash 1017 | yes (`deepseek-ai/DeepSeek-V4.1-Flash-1017`) | yes | yes | 0.3 / 1.2 |
| `reflection/Beam-1.0` | Beam | yes (`reflection/Beam-1.0-501B-A23B-NVFP4`) | no | yes | 0.4 / 1.2 |
| `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B` | Nemotron Ultra | not stated | no | yes | 0.6 / 2.4 |
| `deepseek-ai/DeepSeek-V4.1-Flash-Fast` | DeepSeek V4.1 Flash Fast | yes (`deepseek-ai/DeepSeek-V4.1-Flash`) | yes | yes | 0.6 / 2.4 |
| `deepseek-ai/DeepSeek-V4.1-Flash-1017-Fast` | DeepSeek V4.1 Flash 1017 Fast | yes (`deepseek-ai/DeepSeek-V4.1-Flash-1017`) | yes | yes | 0.6 / 2.4 |
| `meta-models/muse-spark-open` | Muse Spark Open | yes (`meta-models/Muse-Spark-Open-816B-A42B-NVFP4`) | yes | yes | 1.25 / 4.25 |
| `meta-models/muse-spark-open-1026` | [HACKATHON] Muse Spark Open | yes (`meta-models/Muse-Spark-Open-816B-A42B-NVFP4`) | yes | yes | 1.25 / 4.25 |
| `deepseek-ai/DeepSeek-V4-Pro-0813` | DeepSeek V4 Pro 0813 | not stated | no | yes | 1.32 / 3.96 |
| `zai-org/GLM-5.2` | GLM 5.2 | yes (`zai-org/GLM-5.2`) | yes | yes | 1.4 / 4.4 |
| `zai-org/GLM-5.3` | GLM 5.3 | yes (`zai-org/GLM-5.3`) | yes | yes | 1.4 / 4.4 |
| `zai-org/GLM-5.2-Fast` | GLM 5.2 Fast | yes (`zai-org/GLM-5.2`) | yes | yes | 2.1 / 6.6 |
| `zai-org/GLM-5.3-Fast` | GLM 5.3 Fast | yes (`zai-org/GLM-5.3`) | yes | yes | 2.1 / 6.6 |
| `moonshotai/Kimi-K3` | Kimi K3 | yes (`moonshotai/Kimi-K3`) | yes | yes | 3 / 15 |

The `decision-models/*` entries list no tool support, so they cannot run the tool-calling test.
