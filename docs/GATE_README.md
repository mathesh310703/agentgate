# agentgate package: quick use

```python
from agentgate import Gate, Session, default_workspace_policy

policy = default_workspace_policy()
gate = Gate(policy)
session = Session("Summarise my unread emails", policy)      # the only trusted text

session.add_tool_output("get_unread_emails", email_text)      # untrusted text
session.add_pixels(ocr_text_of_screenshot, "invoice.png")     # untrusted pixels (see agentgate/pixels.py)

decision = gate.check("send_email", {"recipients": ["x@y.test"], "subject": "s", "body": "b"}, session)
if decision.action != "allow":
    print(decision.explain())    # plain-language reason, names the origin
```

Decisions: `allow`, `block`, `ask` (destructive action on a target the user did not name).
Run tests: `python tests/test_gate.py`.

Files: labels.py (origins), normalize.py (matching), policy.py (risky tools, trusted sources),
session.py (records), gate.py (decision), pixels.py (OCR, optional dependency).
Not written yet: the AgentDojo adapter, the screenshot-agent harness, the MCP wrapper.
