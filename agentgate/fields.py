"""Split a structured tool result into structured leaves and free-text leaves.

Structured leaves (participants, sender, recipients, a contact's email, ids, keys such as shared_with
addresses) are values the tool's data model puts in a typed slot. Free-text leaves (description, body,
content, subject, title) are prose anyone who can write to the object controls, which is where
injections live. Only structured leaves can act as a trusted source.
"""

import re

FREE_TEXT_FIELDS = frozenset({"description", "body", "content", "subject", "title"})
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def is_id_field(name: str) -> bool:
    n = (name or "").lower().rstrip("_")
    return n == "id" or n.endswith("_id")


def _plain(obj):
    dump = getattr(obj, "model_dump", None)   # pydantic models (AgentDojo tool results)
    return dump(mode="json") if callable(dump) else obj


def leaves(obj, free_text_fields=FREE_TEXT_FIELDS):
    """Yield (field, value, part) for every scalar leaf; part is "structured" or "free_text".
    `field` is the nearest enclosing key ("" at top level)."""
    for field, value, part, _ in leaves_with_entry(obj, free_text_fields):
        yield field, value, part


def leaves_with_entry(obj, free_text_fields=FREE_TEXT_FIELDS):
    """Like leaves(), plus `entry`: the index of the nearest enclosing dict, so values of one listing
    entry (a file's id_ and size) can be grouped. -1 when the leaf is not inside a dict."""
    counter = [0]

    def walk(o, key, free, entry):
        o = _plain(o)
        if isinstance(o, dict):
            here = counter[0]
            counter[0] += 1
            for k, v in o.items():
                k = str(k)
                if not free and not _IDENT.fullmatch(k):   # data-bearing keys, e.g. shared_with addresses
                    yield key, k, "structured", entry
                yield from walk(v, k, free or k.lower() in free_text_fields, here)
        elif isinstance(o, (list, tuple, set)):
            for v in o:
                yield from walk(v, key, free, entry)
        elif o is not None and str(o).strip():
            yield key, str(o), "free_text" if free else "structured", entry

    obj = _plain(obj)
    if not isinstance(obj, (dict, list, tuple, set)):   # a bare string or number is prose, not a record
        return
    yield from walk(obj, "", False, -1)
