"""Optional attachment policy (off by default), added after the adaptive report (eval/ADAPTIVE_V0.md, cases
#36 and #37): the frozen workspace policy plus send_email's `attachments` as a checked id argument, traced like
share_file's `file_id`. send_email is not destructive, so the ask for untraced destructive ids does not apply:
an attachment id from a trusted listing is allowed, one found only in untrusted text is blocked.

Gate code is unchanged. AgentDojo passes attachments as dicts ({"type": "file", "file_id": "19"} or
{"type": "event", "event_details": {...}}), and the frozen gate would flatten a dict into all of its values
("file" included). AttachGate therefore hands the gate only the file ids; the tool still gets the original
arguments. Event attachments are not checked: their content is composed by the agent, not a stored target.

    gate = AttachGate(attach_policy())
"""

from .gate import Gate
from .policy import ToolRule, default_workspace_policy


def attach_policy():
    p = default_workspace_policy()
    p.rules["send_email"] = ToolRule({**p.rules["send_email"].sensitive, "attachments": "id"})
    return p


def attachment_ids(value) -> list:
    """File ids (or bare names) of the attachments; event attachments are skipped."""
    out = []
    for a in value or []:
        if isinstance(a, dict):
            if a.get("type") == "event":
                continue
            out.append(a.get("file_id", a))   # a dict without file_id is checked whole
        else:
            out.append(a)
    return out


def attach_args(tool: str, args: dict) -> dict:
    if tool == "send_email" and args and args.get("attachments"):
        return {**args, "attachments": attachment_ids(args["attachments"])}
    return args


class AttachGate(Gate):
    def check(self, tool, args, session):
        return super().check(tool, attach_args(tool, args), session)
