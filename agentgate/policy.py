"""Which tools are risky, which of their arguments pick the target, and which sources are trusted."""

from dataclasses import dataclass, field


@dataclass
class ToolRule:
    # argument name -> kind ("recipient", "id", "amount", "url")
    sensitive: dict
    # destructive tools: an id that is not named by the user returns "ask" instead of "allow"
    confirm_untraced_ids: bool = False


@dataclass
class Policy:
    rules: dict = field(default_factory=dict)
    # kind -> tools whose output may be trusted as a source for that kind of argument
    # (for example, a contact search is a trusted source of recipients).
    trusted_for: dict = field(default_factory=dict)
    # True: a sensitive value found nowhere (neither user nor trusted source) is blocked.
    block_unknown: bool = True

    def is_trusted_source(self, tool: str, kind: str) -> bool:
        return tool in self.trusted_for.get(kind, set())


def default_workspace_policy() -> Policy:
    """Policy for the AgentDojo 'workspace' suite. Edit freely; measured by false-block rate."""
    contacts = {"search_contacts_by_name", "search_contacts_by_email"}
    listings = {
        "list_files", "search_files", "search_files_by_filename",
        "get_unread_emails", "search_emails", "get_received_emails",
        "get_sent_emails", "get_draft_emails",
        "search_calendar_events", "get_day_calendar_events",
    }
    rules = {
        "send_email": ToolRule({"recipients": "recipient", "cc": "recipient", "bcc": "recipient"}),
        "share_file": ToolRule({"email": "recipient", "file_id": "id"}),
        "delete_file": ToolRule({"file_id": "id"}, confirm_untraced_ids=True),
        "delete_email": ToolRule({"email_id": "id"}, confirm_untraced_ids=True),
        "create_calendar_event": ToolRule({"participants": "recipient"}),
        "add_calendar_event_participants": ToolRule({"participants": "recipient", "event_id": "id"}),
        "cancel_calendar_event": ToolRule({"event_id": "id"}, confirm_untraced_ids=True),
        "reschedule_calendar_event": ToolRule({"event_id": "id"}),
        # banking / slack style tools, if those suites are run later
        "send_money": ToolRule({"recipient": "recipient", "amount": "amount"}),
        "schedule_transaction": ToolRule({"recipient": "recipient", "amount": "amount"}),
        "update_scheduled_transaction": ToolRule({"recipient": "recipient", "amount": "amount"}),
        "send_direct_message": ToolRule({"recipient": "recipient"}),
        "invite_user_to_slack": ToolRule({"user_email": "recipient"}),
        "post_webpage": ToolRule({"url": "url"}),
        "get_webpage": ToolRule({"url": "url"}),
    }
    return Policy(
        rules=rules,
        trusted_for={"recipient": contacts, "id": listings},
    )
