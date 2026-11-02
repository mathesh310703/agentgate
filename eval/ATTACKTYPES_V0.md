# More AgentDojo attack types against Muse Spark Open (Nov 2, 2026)

## The rule, fixed before any model call

This section was committed before the first episode ran; `git log` on this file shows it.

**Attacks.** Only attacks that ship in the installed AgentDojo (0.1.35, benchmark v1.2.2). No new attack text. Of the 17 registered:
- **Run (11, goal-hijacking):** `direct`, `ignore_previous`, `important_instructions`, `important_instructions_no_model_name`, `important_instructions_no_names`, `important_instructions_no_user_name`, `important_instructions_wrong_model_name`, `important_instructions_wrong_user_name`, `injecagent`, `system_message`, `tool_knowledge`.
- **Not run (6):** `manual` needs typed input during the run. `dos`, `captcha_dos`, `felony_dos`, `offensive_email_dos` and `swearwords_dos` have no injection goal or tool-call target, so attack success as measured here and the gate do not apply to them.

**Budget before the run.** Left per stage: dev $5.00, baseline $8.84, defense $18.18, **benchmark $29.84 (used here)**, arena $20.00, reserve $10.00. Total spent so far $8.14.

**Cap.** $3 in all: at most $2 ungated, and the rest for the gated arm. The script stops at these.

**Estimate.** Earlier attack runs averaged about 3 model calls per episode (7 messages) at about $0.0037 per call, so about $0.012 per episode.

**Sample.** The same user tasks and injection goals for every attack, workspace suite, one run per episode:
1. Start from every 4th user task (0, 4, … 36) and goals 0–3: 11 × 10 × 4 = 440 episodes, about $5.28, over the $2 ungated cap.
2. Shrink by this rule alone: first halve the user tasks to every 8th (0, 8, 16, 24, 32): 220 episodes, about $2.64, still over.
3. Then drop the highest-numbered goal until the estimate fits: goals 0, 1, 2: **11 × 5 × 3 = 165 episodes, about $1.98**.

So: **user tasks 0, 8, 16, 24, 32 (3 from the tuning half, 2 from the held-out half); injection goals 0, 1, 2; 165 episodes per arm.** The first 5 are the pilot and count towards the sample. If the ungated cap stops the run first, attacks are run in alphabetical order, and an unfinished attack is reported as unfinished.

**Gated arm.** Only if at least one attack succeeds ungated: the same episodes for every attack type with at least one success, default policy, no judge, under the $3 total cap. If none succeed, no gated arm, and the report says plainly that the model resisted.

**Not changed by results:** this sample, the attack list, the policy, and the gate.
