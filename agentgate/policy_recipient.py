"""Optional recipient-trust layer (off by default), added after the model-driven red-team (eval/REDTEAM_MUSESPARK_V0.md):
a recipient whose only trusted source is an email 'sender' field or a file 'owner' field is not trusted. The call
becomes 'ask' unless the user's own request named the recipient. Everything else is unchanged.

The red-team showed the model attacker reaching the frozen gate's #28 gap in 30/90 episodes by placing its own
address in a sender/owner field, which the default gate trusts for a recipient. This layer closes that, at the cost
of asking on legitimate "reply to the sender" style calls where the address is known only from the sender/owner field.

Frozen files are unchanged. `downgrade()` is a pure function the scripts apply after Gate.check; RecipientGate is a
convenience subclass for tests and the MCP server.

    gate = RecipientGate(default_workspace_policy())
    # or, after an existing gate's decision:
    decision = downgrade(gate.check(tool, args, session), tool, args, session, policy)
"""

from .gate import Decision, Gate, _atoms
from .labels import Origin

# the structured fields whoever sent or shared an item chooses (same set the frozen policy calls attacker_fields)
SENDER_OWNER_FIELDS = frozenset({"sender", "owner"})
RECIPIENT_KINDS = frozenset({"recipient"})


def _sender_owner_only(session, atom, kind) -> str:
    """If this recipient atom is trusted only through a structured sender/owner field (and the user did not name it),
    return that field's source (e.g. 'get_received_emails.sender'); otherwise ''."""
    recs = session.find(atom)
    if any(r.origin == Origin.USER for r in recs):
        return ""                                   # the user named it: the frozen gate's own "ok", left alone
    trusted = [r for r in recs if session.trusted_for(r, kind, atom)]
    if not trusted:
        return ""                                   # not trusted at all: the frozen gate already did not allow on this
    if all(r.part == "structured" and (r.field or "").lower().rstrip("_") in SENDER_OWNER_FIELDS for r in trusted):
        return trusted[0].where
    return ""                                       # at least one trusted source is something else (e.g. a contact search)


def recipient_from_sender_owner(tool, args, session, policy):
    """The first (arg, atom, source) whose recipient is trusted only via a sender/owner field, or None."""
    rule = policy.rules.get(tool)
    if rule is None:
        return None
    for arg, kind in rule.sensitive.items():
        if kind not in RECIPIENT_KINDS:
            continue
        for atom in _atoms((args or {}).get(arg)):
            source = _sender_owner_only(session, atom, kind)
            if source:
                return arg, atom, source
    return None


def downgrade(decision: Decision, tool, args, session, policy) -> Decision:
    """Turn an 'allow' into an 'ask' when a recipient is trusted only through a sender/owner field. Never the reverse,
    and a 'block' or 'ask' is left as it is."""
    if decision.action != "allow":
        return decision
    hit = recipient_from_sender_owner(tool, args, session, policy)
    if hit is None:
        return decision
    arg, atom, source = hit
    return Decision(
        "ask", tool,
        f"'{tool}': the recipient {arg}='{atom}' is trusted only because it appears in a '{source}' field, which "
        f"whoever sent or shared the item chooses, and you did not name it in your request. Please confirm.",
        decision.findings,
    )


class RecipientGate(Gate):
    """The frozen gate, plus the optional recipient-trust layer."""

    def check(self, tool, args, session):
        return downgrade(super().check(tool, args, session), tool, args, session, self.policy)
