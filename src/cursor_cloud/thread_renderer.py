"""Discord thread chat-room rendering (activity vs final messages)."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .models import DISCORD_MESSAGE_LIMIT, RunSnapshot, RunStatus, ToolActivity
from .status_renderer import (
    _boundary_at_or_before,
    format_live_peek,
    normalize_headings,
    redact_untrusted,
    tool_family,
    truncate_message,
)

# Re-export for callers that historically imported from this module.
__all__ = [
    "THREAD_THINKING_INDICATOR",
    "format_thread_chat_info",
    "github_hint_from_snapshot",
    "render_thread_activity",
    "render_thread_final",
    "render_thread_summary",
    "tool_family",
]

_FAMILY_EMOJI: dict[str, str] = {
    "search": "🔍",
    "read": "📖",
    "edit": "✏️",
    "write": "📝",
    "shell": "🐚",
}
_FAILED_STATUSES = frozenset({"failed", "error", "cancelled", "canceled"})

# Immediate ack while a thread follow-up is preparing / waiting on the API.
THREAD_THINKING_INDICATOR = "<a:aithinking:1527850620273430548> *thinking...*"


def _coalesce_tools(tools: Iterable[ToolActivity]) -> list[str]:
    """Render concise rolling tool summaries grouped by family."""
    by_family: dict[str, list[ToolActivity]] = defaultdict(list)
    for tool in tools:
        by_family[tool_family(tool.name)].append(tool)

    lines: list[str] = []
    for family in sorted(by_family.keys()):
        group = by_family[family][-6:]
        count = len(group)
        latest = group[-1]
        summary = redact_untrusted(latest.summary or latest.name)[:100]
        if count > 1:
            lines.append(
                f"- `{family}` ×{count} ({latest.status}) {summary}".rstrip()
            )
        else:
            lines.append(
                f"- `{latest.name}` ({latest.status}) {summary}".rstrip()
            )
    return lines


def github_hint_from_snapshot(
    snapshot: RunSnapshot,
    *,
    repository_url: str | None = None,
) -> str | None:
    """Compact github hint: branch name, else owner/repo from repository URL."""
    for branch in list(snapshot.git_branches or []):
        name = str(branch.branch or "").strip()
        if name:
            return name
    url = str(repository_url or "").strip().rstrip("/")
    if not url:
        return None
    if "github.com/" in url:
        tail = url.split("github.com/", 1)[-1]
        if tail.endswith(".git"):
            tail = tail[:-4]
        return tail or None
    return url.rsplit("/", 1)[-1] or None


def format_thread_chat_info(
    *,
    agent_id: str,
    model: str | None = None,
    branch: str | None = None,
) -> str:
    """Multiline session header for the first thread final only."""
    lines = [
        "### Chat Info",
        f"- id: `{redact_untrusted(agent_id)[:80]}`",
    ]
    branch_text = str(branch or "").strip()
    if branch_text:
        lines.append(f"- branch: `{redact_untrusted(branch_text)[:80]}`")
    model_text = str(model).strip() if model else ""
    model_disp = redact_untrusted(model_text)[:60] if model_text else "auto"
    lines.append(f"- model: `{model_disp}`")
    return "\n".join(lines)


def render_thread_summary(snapshot: RunSnapshot) -> str:
    """Post-run summary: thinking duration, subagents, and tool-family totals."""
    parts: list[str] = []

    seconds = snapshot.thinking_seconds
    if seconds is not None and seconds > 0:
        secs = max(1, int(round(float(seconds))))
        parts.append(f"💭 Thought for {secs}s")

    subagents = list(snapshot.subagents or [])
    if subagents:
        parts.append("### Subagents")
        for index, agent in enumerate(subagents, start=1):
            status_l = str(agent.status or "").lower()
            emoji = "🔴" if status_l in _FAILED_STATUSES else "🟢"
            label = redact_untrusted(agent.label or "").strip()[:80]
            if label and not label.lower().startswith("subagent "):
                parts.append(f"{emoji} Subagent {index}: {label}")
            else:
                parts.append(f"{emoji} Subagent {index}")

    counts = {
        str(family): int(count)
        for family, count in (snapshot.tool_family_counts or {}).items()
        if family != "subagent" and int(count) > 0
    }
    if counts:
        parts.append("### Tool Calls")
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        for family, count in ordered:
            emoji = _FAMILY_EMOJI.get(family, "🔧")
            parts.append(f"{emoji} `{family}` ×{count}")

    return "\n".join(parts)


def render_thread_activity(
    snapshot: RunSnapshot,
    *,
    agent_name: str | None = None,
    skipped_images: list[str] | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Editable in-flight Activity: thinking + grouped tools only (no run/git chrome)."""
    del agent_name  # unused — kept for call-site compatibility with classic sink
    lines: list[str] = []
    has_live_progress = False

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        lines.append("### Error")
        lines.append(redact_untrusted(snapshot.error_message)[:500])

    tools = list(snapshot.tools[-12:])
    if tools:
        lines.append("### Activity")
        lines.extend(_coalesce_tools(tools))
        has_live_progress = True

    if snapshot.status.is_active and snapshot.thinking_text:
        peek = format_live_peek(
            redact_untrusted(snapshot.thinking_text),
            head_chars=140,
            tail_chars=280,
        )
        if peek:
            lines.append("### Thinking")
            lines.append(peek)
            has_live_progress = True

    if snapshot.status.is_active and snapshot.assistant_text:
        peek = format_live_peek(
            redact_untrusted(snapshot.assistant_text),
            head_chars=120,
            tail_chars=240,
        )
        if peek:
            lines.append("")
            lines.append(f"_Draft…_ {peek}")
            has_live_progress = True

    if skipped_images:
        lines.append("")
        lines.append("### Images")
        for note in skipped_images[:5]:
            lines.append(f"- {redact_untrusted(note)[:160]}")

    if snapshot.degraded:
        lines.append("_Activity updates degraded; some edits may have failed._")

    if not lines:
        if snapshot.status.is_terminal:
            # Clear activity chrome; the frozen final message carries the answer.
            # Discord rejects empty message content, so use a zero-width space.
            return "\u200b"
        lines.append(THREAD_THINKING_INDICATOR)
    elif snapshot.status.is_active and not has_live_progress:
        # Ancillary notes alone (e.g. skipped images) must not look like a dead pause.
        lines.insert(0, THREAD_THINKING_INDICATOR)

    text = "\n".join(lines).strip()
    text, _ = truncate_message(text, limit=limit)
    return normalize_headings(text)[:limit]


def render_thread_final(
    snapshot: RunSnapshot,
    *,
    agent_name: str | None = None,
    skipped_images: list[str] | None = None,
    chat_info: str | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Frozen final answer/error only — no Finished/Agent/Run/Git/Duration chrome.

    May exceed a single Discord message; the thread sink splits into at most two
    posts. Soft-capped at ``2 * limit`` so translators still see a bounded body.
    """
    del agent_name  # unused — kept for call-site compatibility
    max_len = max(limit, limit * 2)

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        text = "### Error\n" + redact_untrusted(snapshot.error_message)[:1500]
        text = normalize_headings(text)
        if len(text) <= max_len:
            return text
        return text[:max_len]

    body = snapshot.result_text or snapshot.assistant_text
    if not body:
        return "_No output._"

    text = redact_untrusted(body)
    if chat_info:
        text = f"{chat_info.strip()}\n\n{text}"
    if skipped_images:
        notes = "\n".join(
            f"- {redact_untrusted(note)[:160]}" for note in skipped_images[:5]
        )
        text = f"{text}\n\n_Images skipped:_\n{notes}"

    text = normalize_headings(text)
    if len(text) <= max_len:
        return text
    # Prefer a clean break so the sink can split without mid-word cuts.
    cut = _boundary_at_or_before(text, max_len, min_keep=max(24, max_len // 4))
    if cut < max(24, max_len // 4):
        cut = max_len
    return text[:cut].rstrip()
