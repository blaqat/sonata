"""Match bot whitelist entries by id, username, or display name."""


def author_in_whitelist(author, whitelist) -> bool:
    """Return True if *author* matches a whitelist entry.

    Entries may be a numeric id (exact equality) or a name string matched
    case-insensitively against ``author.name`` and ``author.display_name``.
    """
    if not whitelist:
        return False

    author_id = getattr(author, "id", None)
    names = set()
    for attr in ("name", "display_name"):
        value = getattr(author, attr, None)
        if isinstance(value, str) and value:
            names.add(value.casefold())

    for entry in whitelist:
        if author_id is not None and entry == author_id:
            return True
        if isinstance(entry, str) and entry.casefold() in names:
            return True
    return False
