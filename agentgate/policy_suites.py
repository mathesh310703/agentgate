"""Policies for the banking, slack and travel AgentDojo suites. Tuned AFTER seeing the out-of-distribution
replay with the frozen workspace policy (eval/SUITES_V0.md, first table); its numbers are therefore not a
held-out result. Gate code is unchanged: this file only builds Policy objects for Gate(policy).

Two levels:
  "rules"        the frozen default policy plus rules for the write tools that had none
  "rules_trust"  "rules" plus per-suite trust settings: no structured field of a tool result vouches for a
                 recipient in travel and slack (review dicts keyed by hotel name, and channel-name lists,
                 carried injected addresses into "structured" leaves)

Kinds used here besides the default ones: "user_value" (a password or profile field: only the user's
request vouches for it) and "venue" (a hotel, restaurant or car-rental company: the user's request or the
suite's city listing tools vouch for it).
"""

from .policy import ToolRule, default_workspace_policy

NEW_RULES = {
    "banking": {
        "update_password": ToolRule({"password": "user_value"}),
        "update_user_info": ToolRule({"first_name": "user_value", "last_name": "user_value", "street": "user_value",
                                      "city": "user_value"}),
    },
    "slack": {
        "add_user_to_channel": ToolRule({"user": "recipient", "channel": "recipient"}),
        "remove_user_from_slack": ToolRule({"user": "recipient"}),
        "send_channel_message": ToolRule({"channel": "recipient"}),
    },
    "travel": {
        "reserve_hotel": ToolRule({"hotel": "venue"}),
        "reserve_car_rental": ToolRule({"company": "venue"}),
        "reserve_restaurant": ToolRule({"restaurant": "venue"}),
    },
}
VENUE_LISTINGS = {"get_all_hotels_in_city", "get_all_restaurants_in_city", "get_all_car_rental_companies_in_city"}


def suite_policy(suite: str, level: str = "rules"):
    p = default_workspace_policy()
    p.rules.update(NEW_RULES.get(suite, {}))
    if suite == "travel":
        p.trusted_for["venue"] = set(VENUE_LISTINGS)
    if level == "rules_trust" and suite in ("travel", "slack"):
        p.structured_trust = frozenset({"id"})
        if suite == "slack":   # channel membership lists are the suite's directory of users
            p.trusted_for["recipient"] = {"get_users_in_channel"}
    return p
