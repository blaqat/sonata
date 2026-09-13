"""Shared classification of Cursor stream-gone / stream-unavailable errors."""

from __future__ import annotations

from typing import Any

STREAM_UNAVAILABLE_CODES = frozenset(
    {"stream_expired", "stream_unavailable", "gone"}
)

# Shared needles for message-based stream-gone detection (client + tracker).
STREAM_UNAVAILABLE_NEEDLES = (
    "no longer available",
    "stream expired",
    "stream is no longer",
    "stream unavailable",
    "run stream is no longer",
)


def stream_unavailable_text(value: Any) -> str:
    """Flatten nested SSE/API error payloads into searchable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = [
            stream_unavailable_text(value.get("message")),
            stream_unavailable_text(value.get("error")),
            stream_unavailable_text(value.get("text")),
            stream_unavailable_text(value.get("code")),
        ]
        return " ".join(p for p in parts if p)
    return str(value)


def is_stream_unavailable_error(data: dict[str, Any] | None) -> bool:
    """True when an SSE error means the stream ended, not that the agent failed."""
    payload = data or {}
    code = str(payload.get("code") or "").lower()
    message = stream_unavailable_text(payload).lower()
    if code in STREAM_UNAVAILABLE_CODES:
        return True
    return any(n in message for n in STREAM_UNAVAILABLE_NEEDLES)


def looks_like_stream_unavailable(exc: BaseException) -> bool:
    """True when a client exception looks like a dropped/unreadable stream."""
    code = str(getattr(exc, "code", "") or "").lower()
    message = " ".join(
        str(part)
        for part in (exc, getattr(exc, "user_message", ""), getattr(exc, "message", ""))
        if part
    ).lower()
    if code in STREAM_UNAVAILABLE_CODES:
        return True
    return any(n in message for n in STREAM_UNAVAILABLE_NEEDLES)


def is_stream_unavailable_exc(exc: BaseException) -> bool:
    """True when a client exception is a dropped/unreadable stream, not agent failure.

    Broader than :func:`looks_like_stream_unavailable` — also treats
    ``transport_error`` as stream-gone so the tracker can poll GET run.
    """
    code = str(getattr(exc, "code", "") or "").lower()
    message = " ".join(
        str(part)
        for part in (exc, getattr(exc, "user_message", ""), getattr(exc, "message", ""))
        if part
    ).lower()
    if code in STREAM_UNAVAILABLE_CODES or code == "transport_error":
        return True
    return is_stream_unavailable_error({"code": code, "message": message})
