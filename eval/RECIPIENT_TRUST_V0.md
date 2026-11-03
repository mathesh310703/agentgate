# Optional recipient-trust layer against the sender/owner gap (Nov 3, 2026)

**Result: the layer closes the gap and costs nothing on the workspace tasks the repo supports. It is optional and off by default.** It was built on branch `recipient-trust-v0` after the model-driven red-team (`eval/REDTEAM_MUSESPARK_V0.md`) showed the frozen gate's #28 sender/owner trust reached in 30/90 episodes. With the layer on, all 30 saved bypass calls become `ask`, a fresh 90-episode model attack bypasses it **0 times (0.0–4.1%)**, and a held-out workspace replay shows **0 legitimate calls newly asked or blocked**.

This does not change the frozen gate. The layer is a new optional module, `agentgate/policy_recipient.py`, applied only when asked for.

## The rule

For a recipient-type argument (`send_email` recipients/cc/bcc, `share_file` email — any argument the policy types as `recipient`), a value whose **only** trusted source is an email `sender` field or a file `owner` field is not trusted. The call becomes **`ask`** unless the user's own request named the recipient. Everything else is unchanged: a recipient the user named, or one from a genuinely trusted source such as a contact search, stays `allow`; a recipient from untrusted free text stays `block`; ids, amounts and urls are untouched; and the layer never turns a `block` or `ask` into `allow`.

`sender` and `owner` are the fields the frozen policy already calls `attacker_fields` — the ones whoever sent or shared an item chooses. The default gate trusts them for a recipient; with no Layer 1 detector its sender/owner rule never fires (`eval/LAYER1_86M.md`), which is the hole the red-team walked through.

## Utility cost

Worst-case replay on the held-out half of AgentDojo workspace (tasks 20–39), the layer off vs on, judge off. Every gate decision is **identical** with the layer off and on, so the layer adds **0** asks and **0** blocks.

| replay | user calls | blocked (off → on) | asked (off → on) | utility (off → on) |
|---|---|---|---|---|
| clean (legitimate only) | 44 | 0 → 0 | 2 → 2 | 18/20 → 18/20 |
| under attack | 616 | 0 → 0 | 28 → 28 | 252/280 → 252/280 |

- **Legitimate calls that became `ask` or `block`: none.** The 28 held-out legitimate asks under attack are the pre-existing destructive-id asks (`delete_file` with a `file_id` from a listing the user did not name); the layer does not touch them. Attack success stays 0/280.
- **Why the cost is zero here:** no legitimate recipient in these workspace tasks is known only from a `sender`/`owner` field. They come from the user's request or a contact search.
- **Where it would cost:** a genuine "reply to the sender of this email" task, where the only source of the address is the `sender` field, would become an `ask`. The workspace suite's held-out tasks contain no such case, so the measured cost is 0; a mailbox assistant built on reply-to-sender would see asks. A unit test pins this behaviour on purpose (`tests/test_recipient_trust.py`).

## Fresh attack with the layer on

`eval/redteam_musespark.py` rerun with the layer on, a new seed (`s1`, mixed into every attacker prompt), the same 3 goals × 3 channels × 10 episodes, Muse Spark Open as the attacker through `agentlab/proxy.py`, up to 5 rounds, getting the gate's reason after each block. The layer was **not** tuned to the results.

| cut | bypassed episodes |
|---|---|
| **all** | **0/90 (0.0-4.1%)** |
| goal: share the canary | 0/30 (0.0-11.4%) |
| goal: email the attacker | 0/30 (0.0-11.4%) |
| goal: delete the canary | 0/30 (0.0-11.4%) |
| channel: tool text (email `sender`) | 0/30 (0.0-11.4%) |
| channel: file text (file `owner`) | 0/30 (0.0-11.4%) |
| channel: image text (pixels) | 0/30 (0.0-11.4%) |

Wilson 95% intervals. 90 episodes, 149 scored attempts, **0 refusals, 0 attacker errors**, $2.23, stage `arena`. Average rounds to the first block: 1.49.

**No bypass.** With the layer on, every recipient the attacker could reach through a `sender`/`owner` field now returns `ask`, which is not a bypass, so there is nothing to quote. The attacker still had five rounds and the gate's reasons, and found no other path in these channels: the only trusted sources it controls are the `sender`/`owner` fields, and the layer removes them. Against the earlier run's **30/90 (24.5–43.6%)** on the same harness, this is 0/90.

## Limits, stated plainly

- **Not blind.** The layer was written after seeing the first red-team, to close exactly the gap it found. This measures that it closes that gap and what it costs, not that it is robust to an unseen attack.
- **One attacker model, small clustered sample.** Only Muse Spark Open at temperature 0.7; 90 episodes over 3 goals × 3 channels, 10 each, five rounds. The 0/90 interval (0.0–4.1%) is not a guarantee; a different model, more rounds, or a channel that carries a different trusted source could still get through.
- **It only moves the gap to a confirmation.** `ask` is a block in a benchmark, but in a real deployment it asks the user, who can still approve the wrong thing.
- **Narrow scope.** It covers recipient-type arguments only. It does nothing for the other known gaps, which were not tested here: #27 (the attacker address already in the user's contacts — a contact search would still vouch), #29 (the plus-address boundary), #33 and #34 (id typing). Those need separate work.
- **Utility measured on one suite.** The 0-cost result is the held-out workspace half only. Reply-to-sender workflows, and other suites, would see asks; they were not measured.
- **Off by default.** Nothing in the frozen gate, the default policy or the default configuration changed. The layer runs only when explicitly enabled.

## Reproduce

```
# utility (offline, no model):
.venv\Scripts\python scripts/run_worstcase.py --split heldout --mode clean --out runs/recipient_trust_v0/clean_off
.venv\Scripts\python scripts/run_worstcase.py --split heldout --mode clean --recipient-trust --out runs/recipient_trust_v0/clean_on
.venv\Scripts\python scripts/run_worstcase.py --split heldout --out runs/recipient_trust_v0/attack_off
.venv\Scripts\python scripts/run_worstcase.py --split heldout --recipient-trust --out runs/recipient_trust_v0/attack_on
# fresh attack (about $2.20, stage arena):
.venv\Scripts\python -m agentlab.proxy --stage arena
.venv\Scripts\python eval/redteam_musespark.py run --out runs/redteam_recipient_v0 --recipient-trust --seed s1
.venv\Scripts\python eval/redteam_musespark.py summary --out runs/redteam_recipient_v0 --recipient-trust
```
