"""AgentGate: a deterministic action gate with provenance, including provenance through pixels.

Written from scratch for the Meta Global AI Developer Hackathon (Oct 2026).
"""

from .labels import Origin
from .policy import Policy, ToolRule, default_workspace_policy
from .session import Session
from .gate import Decision, Gate

__all__ = [
    "Origin", "Policy", "ToolRule", "default_workspace_policy",
    "Session", "Decision", "Gate",
]
__version__ = "0.1.0"
