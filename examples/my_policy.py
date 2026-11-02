"""Example of your own gate policy: the default workspace policy, but contact search results no longer vouch for a
recipient (adaptive case #27 in eval/ADAPTIVE_V0.md). Run it with the worst-case replay:

  python scripts/run_worstcase.py --split tune --policy examples.my_policy:build --out runs/my_policy
"""

from agentgate import default_workspace_policy


def build():
    policy = default_workspace_policy()
    policy.trusted_for["recipient"] = set()
    return policy
