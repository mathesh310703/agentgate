# Zero-config policy synthesis (Nov 2, 2026)

## The rule, fixed before any model call

This section was committed before the first generation call; `git log` on this file shows it.

**A correction to the brief.** The task said unknown tools "stay blocked as before". They are not blocked today: the frozen `Gate` returns `allow` for any tool without a rule (`agentgate/gate.py:67-68`). The frozen gate is not changed. Fail-closed behaviour is new, and only in the optional `SynthGate` (`agentgate/policy_synth.py`), which blocks every tool that a synthesized policy does not classify. A test pins both behaviours.

**Input to the model.** One call per tool, holding only that tool's name, description and argument JSON schema. No task text, attacks or outcomes. One call per tool means a bad reply costs one tool, not a suite. Temperature 0, `reasoning_effort` low, `max_tokens` 1500, through the proxy, stage `defense`. The system prompt is `SYSTEM` in `agentgate/policy_synth.py`, and each file carries a copy.

**"Destructive" is per tool**, because `ToolRule.confirm_untraced_ids` is per tool. The brief's wording could also be read as per argument.

**Validation.** A reply must meet a fixed JSON schema: exactly the keys `tool`, `risky`, `destructive`, `arguments`, `reason`; this tool's name; every argument and no others; kinds from `recipient`, `id`, `amount`, `url`, `free_text`. Strict parse, no repair, no retry. Anything else makes the tool **unknown**, which `SynthGate` blocks. A failed call does too.

**The floor,** deterministic and independent of the model. A valid reply that breaks one of these also makes the tool unknown:
1. Only a tool whose name starts with `get_`, `list_`, `read_`, `search_` or `check_` may be called not risky.
2. A risky tool must have at least one checked argument.
3. On a risky tool, an argument named `recipient`, `recipients`, `to`, `cc`, `bcc`, `email`, `user`, `user_email`, `participants`, `account`, `iban`, `url`, `amount`, `id` or `*_id` may not be free text.

The cost is expected and will be reported: any write tool whose arguments are all free text, such as a password change, becomes unknown and is blocked for legitimate calls too.

**What the policy holds.** `ToolRule`s from the kinds (free text unchecked), `confirm_untraced_ids` from destructive, and default trust settings. `trusted_for` is empty, because the model was not asked about sources. The default policy's rules are **not** merged in.

**Freeze.** Each of banking, slack, travel and workspace is generated once (`scripts/synth_policies.py generate`, which refuses to overwrite) to `policies/<suite>.json`. The SHA-256 values are recorded here and committed before any replay. No edits after that, no second round. `.gitattributes` keeps these files' bytes the same on Windows and Linux.

**Measurement.** `scripts/run_suites.py`, the same scripted compromised agent and `important_instructions` attack as before, attack and clean passes, on all four suites (zero model cost). Attack success ungated and gated, legitimate calls blocked or asked, utility. Beside it, re-run the same way: the frozen default policy on all four suites, and `agentgate/policy_suites.py` rules (A) and rules + trust (B) on the other three. Wilson 95% intervals.

**Tuned or not.**
- **Synthesized policies:** not tuned on any replay result, since they are frozen before it. They are not blind in every sense: the prompt and the floor were written by someone who had seen these suites' tool names and the earlier results in `eval/SUITES_V0.md`.
- **Frozen default on banking, slack, travel:** not tuned on those suites.
- **Hand-written rules (A) and (B):** tuned on the same pairs they are scored on.
- **Frozen default on workspace:** developed on the workspace tuning half.

**Budget.** Before the run, left per stage: dev $5.00, baseline $8.84, defense $18.18 (used here), benchmark $28.05, arena $20.00, reserve $10.00. Total spent $9.92. Estimate: 74 tools, one call each, about 350 input tokens and up to 1,500 output tokens: about $0.16 expected, $0.50 at worst. The script stops at $1.
