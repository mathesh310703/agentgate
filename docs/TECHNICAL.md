# AgentGate: technical overview

AgentGate is a check that runs before every tool call an AI agent makes. A risky call (send, share, delete, pay) runs only if each of its target arguments traces back to the user's own request or to a trusted structured source. The check is plain code, not a model, and it covers text the agent read from images and screenshots as well as text from tool results. Results are in [RESULTS.md](../RESULTS.md); this page explains how it works and where it stops working.

## Threat model

- **Attacker:**
  - Can write content the agent will read: an email body, a file, a calendar description, a web page, or text drawn into an image, including faint, tiny or ordinary-looking text.
  - Cannot change the user's request, the tool definitions, or the gate.
- **Goal:** make the agent take a side-effecting action the user did not ask for, aimed at a target the attacker chose. For example, share `budget_canary.txt` with `records@corp.test`, or delete file 13.
- **Out of scope:**
  - Attacks that don't need a new target, such as deleting the file the user did name.
  - Wrong answers in plain text: the gate checks actions, not what the agent says.
  - A compromised tool implementation or a malicious user.
- **Fail-closed default:** a target value that can't be traced is blocked. Missing a trace costs a false block, not a leak.

This follows the "Rule of Two" idea (untrusted input, sensitive access and external action should not all meet in one step). It is related to text-side taint gates such as taintgate and agent-policy-gateway, and to screenshot-injection detectors such as SnapGuard; see [RELATED_WORK.md](RELATED_WORK.md). AgentGate was written from scratch. Its addition is carrying provenance through pixels, and measuring that.

## Labels

Every piece of content in a session carries one origin label (`agentgate/labels.py`):

| label | what it covers | trusted? |
|---|---|---|
| `USER` | the user's request | yes |
| `UNTRUSTED_TEXT` | anything a tool returned: emails, files, events, web pages, error messages | no, with the field-aware exceptions below |
| `UNTRUSTED_PIXELS` | text recovered from an image or screenshot by OCR | never |

A `Session` (`agentgate/session.py`) keeps one record per piece of content: its label, its source (`user`, a tool name, or `screenshot:<image>`), its normalised text and, for structured results, the field it sat under.

## The gate, and what "deterministic" means here

`Gate.check(tool, args, session)` (`agentgate/gate.py`) does the following:
1. **Look up the policy** (`agentgate/policy.py`). If the tool isn't on the risky list, allow it; reading is never gated.
2. **Classify each sensitive argument** (recipient, id, amount, url). The value is split into atoms (lists, or comma-separated strings), and each atom is looked up in the session as a whole token, after normalisation (`agentgate/normalize.py`).
   - Normalisation covers Unicode NFKC, zero-width characters, URL and HTML escapes, `[at]`/`(dot)` spellings, case and whitespace.
   - Each atom ends up in one of these classes:
     - **ok:** it appears in the user's request or in a trusted source.
     - **untrusted:** it appears only in untrusted records. The reason names the most specific origin, pixels before text.
     - **unknown:** it appears nowhere.
     - **unnamed:** a number in the request that names a date or an amount, not an id (`agentgate/ids.py`: "June 13" doesn't name file 13).
3. **Decide:**
   - **block:** any argument is untrusted, unknown or unnamed.
   - **ask:** a destructive tool (delete, cancel) targets an id the user didn't name, even if the id is real. In a benchmark nobody can answer, so ask counts as a block.
   - **allow:** everything else.
4. **Explain.** Every decision carries a plain-language reason that names the argument, the value and where it came from. For example: `email='records@corp.test' came from text inside an image or screenshot (screenshot:invoice_00.png)`. In the adapter, the agent gets back: "Action not performed. Do not retry it. Tell the user why: <reason>".

**Deterministic** means: given the same session records and the same call, the decision and the reason text are always the same.
- There is no model, no sampling, no network call and no clock in the decision path.
- The gate's inputs can still vary. OCR output depends on the image and the OCR model, and the agent's calls depend on the agent. That is why OCR text is cached, and why the evaluation replays fixed calls.
- The optional injection-score rule (below) depends on a classifier score. That classifier is the 22M by default, which flags none of our injections at 0.5 (below), so the rule never fires in the reported results.

## Field-aware trust

Treating every tool result as untrusted blocks legitimate work. "Reply to Ana's email" needs Ana's address, which only appears in a tool result. AgentGate therefore splits a structured result into leaves (`agentgate/fields.py`) and trusts some of them:
- **Structured fields** are typed slots in the tool's data model: `sender`, `recipients`, `participants`, a contact's `email`, `id_`, and address keys of a `shared_with` map.
  - They are trusted sources for recipients.
  - For ids, only fields named `id` or `*_id` count.
- **Free-text fields** are prose that anyone who can write to the object controls: `body`, `content`, `description`, `subject`, `title`, and error messages. They are never trusted, even inside a structured result. This is where injections live.
- **Policy-trusted tools** are trusted sources for one kind of value. A contact search, for example, is a trusted source of recipients.

**Known gap:** `sender` and `owner` are structured, but whoever sent or shared the item chooses them. So "reply to the sender" injections pass.
- A rule meant to close this blocks a recipient that comes only from those fields when the session holds free text with an injection score of 0.5 or more.
- That score comes from Llama Prompt Guard 2 (`agentgate/detectors.py`).
- Measured in `eval/LAYER1.md`, at 0.5: 22M flags 0/378 injected tool outputs and 0/60 planted image lines; 86M flags 125/378 and 0/60. Neither has a false positive on the clean set (0/55 outputs, 0/60 OCR texts). The 86M reaches AUC 0.997 on tool outputs and shows no signal on image lines. With the default 22M the rule never fires, so this gap is open.

## The isolated judge

Some legitimate requests produce asks: "delete the largest file" names no id. An optional intent judge (`agentgate/judge.py`, a Muse Spark call through the budget proxy) reviews asks only.

- **What it sees:**
  - the user's request;
  - the tool name and its sensitive arguments;
  - typed facts built from structured fields only: each value's kind, the tool and field it came from, and for an id, the numeric fields of its listing entry (such as size) plus the ids and numeric fields of up to 50 sibling entries.
- **What it never sees:** free text. No bodies, subjects, descriptions, file contents or filenames. An injection lives in free text, so it has no channel to the judge.
- **What it can do:** only turn an ask into an allow. A block never reaches the judge, and an allow is never changed.
- **When it fails:** its reply must be strict JSON `{"decision": "approve"|"deny", "reason": ...}`. Anything else is a deny: a parse error, a timeout, an HTTP error, a budget refusal or extra keys.

## Pixel provenance

`agentgate/pixels.py` runs OCR (RapidOCR, ONNX) three times: on the image, on its inverse, and on an auto-contrast version. The extra passes recover faint and low-contrast text. The recovered lines are added to the session as `UNTRUSTED_PIXELS` under `screenshot:<image>`. OCR is the same 768 px JPEG the model is sent.

OCR drops and inserts spaces ("withreview@corp.test"). So, for pixel records only, an address-like value (an email address or URL of 8+ characters) also matches with all whitespace removed. This is the one disclosed post-freeze fix, tag `gate-final.1`.

If OCR misses the line entirely, the address is not traced at all. The call is still blocked, as an unknown recipient, but the reason can't name the image.

## Evaluation method

- **Worst-case replay** (`scripts/run_worstcase.py`):
  - A scripted compromised agent runs each AgentDojo workspace user task's ground-truth calls, then the injection task's calls. That covers 40 × 14 pairs, with no model.
  - This measures the gate against an agent that always obeys the injection. A real model's refusals therefore can't flatter the result.
  - **Clean mode** (no injections) measures false blocks on the user's own calls.
- **Held-out split:** development and tuning used user tasks 0–19 only. Tasks 20–39 were run once per version.
  - Because an earlier analysis had looked at all 40 tasks, this split is "held out" in the weak sense.
- **Vision worst case** (`eval/vision_demo/worstcase.py`): a scripted agent obeys every hidden image line in two 30-image sets (15 carriers each).
- **Real models:**
  - **Muse Spark Open:** a live clean run of 40 tasks with and without the gate. It is also run under recorded AgentDojo attacks and against image carriers; it refused them all on its own.
  - **Qwen3-VL-2B:** a small open model used as a test subject, which does get fooled. It is run greedy and sampled (temperature 0.7, seeds recorded) on 60 images, plus a 60-image third set with three carrier wordings.
  - Rates come with Wilson 95% intervals.
- **Reproduction:** `scripts/reproduce.py` re-runs the replay and the vision worst case at zero cost, and reads the live cells from committed run files, dated. The offline tests run in CI (`.github/workflows/tests.yml`) with no keys and no model access.

## Limits

- **String matching, not semantics.** A target that is paraphrased, translated, split across fields or encoded isn't traced. It is blocked, which is safe but can be a false block. A value that also appears in a trusted field is trusted.
- **Attacker-chosen structured fields** (`sender`, `owner`) are trusted. The rule meant to cover them never fires with the default 22M (`eval/LAYER1.md`).
- **Ids are untyped.** Any id field vouches for any id argument, so a calendar event's id 13 can make `delete_file('13')` an ask rather than a block. In the evaluation, the judge denied every such ask.
- **OCR recall** drops for very small text: 10 px corner text at 768 px is not recovered. Pixel provenance is only as good as OCR, though missed lines still fail closed.
- **Coverage:** only 6 of 14 AgentDojo workspace injection goals are replayable, because the others ship without ground truth. One suite, synthetic images, and `.test` addresses with a canary file.
- **Evidence for the judge is thin.** It is measured on one task family (deleting a described file).
- **Live runs are single runs.** Run-to-run variance is about ±2 tasks out of 40.
- **What the gate doesn't do:** it doesn't stop an agent from saying something wrong, and it doesn't make a fooled model unfooled. With the gate, Qwen still tried the leak; the call just never ran.
