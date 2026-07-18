"""Thread-session helpers (policy inheritance, follow-up gating)."""

from __future__ import annotations

from typing import Any

from .models import AgentSession


def policy_channel_id(
    *,
    channel_id: str,
    session: AgentSession | None = None,
    parent_channel_id: str | None = None,
) -> str:
    """Channel id used for Sonata policy checks (parent for bound threads)."""
    if session is not None and session.thread_bound and session.parent_channel_id:
        return session.parent_channel_id
    if parent_channel_id:
        return str(parent_channel_id)
    return str(channel_id)


def owner_reply_to_human(message: Any, owner_id: str) -> bool:
    """True when owner replied to another human (not bot/self) — skip agent follow-up."""
    ref = getattr(message, "reference", None)
    if ref is None or getattr(ref, "message_id", None) is None:
        return False
    resolved = getattr(ref, "resolved", None)
    if resolved is None:
        return False
    author = getattr(resolved, "author", None)
    if author is None:
        return False
    if getattr(author, "bot", False):
        return False
    if str(getattr(author, "id", "")) == str(owner_id):
        return False
    return True


def thread_session_immutable_violation(
    session: AgentSession,
    *,
    force_new: bool,
    agent_id: str | None,
) -> bool:
    """Bound threads cannot switch agents mid-thread."""
    if not session.thread_bound:
        return False
    if force_new:
        return True
    if agent_id is not None and agent_id != session.agent_id:
        return True
    return False
