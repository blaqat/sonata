"""Discord thread chat-room rendering (activity vs final messages)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .models import DISCORD_MESSAGE_LIMIT, RunSnapshot, RunStatus, ToolActivity
from .status_renderer import redact_untrusted, truncate_message

# Map tool names to rolling summary families (coalesce repeated calls).
_TOOL_FAMILY_ALIASES: dict[str, str] = {
    "grep": "search",
    "glob_file_search": "search",
    "glob": "search",
    "websearch": "search",
    "Task": "subagent",
    "task": "subagent",
    "Shell": "shell",
    "shell": "shell",
    "Read": "read",
    "read": "read",
    "Write": "write",
    "write": "write",
    "StrReplace": "edit",
    "search_replace": "edit",
}

# Immediate ack while a thread follow-up is preparing / waiting on the API.
THREAD_THINKING_INDICATOR = "### Thinking\n…"


def tool_family(name: str) -> str:
    text = str(name or "tool").strip()
    if not text:
        return "tool"
    if text in _TOOL_FAMILY_ALIASES:
        return _TOOL_FAMILY_ALIASES[text]
    base = text.split("_")[0].lower()
    return _TOOL_FAMILY_ALIASES.get(base, base or "tool")


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


def _normalize_headings(text: str) -> str:
    text = re.sub(r"^##(?!#)\s*", "### ", text, flags=re.MULTILINE)
    text = re.sub(r"^#(?!#)\s*", "### ", text, flags=re.MULTILINE)
    return text


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

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        lines.append("### Error")
        lines.append(redact_untrusted(snapshot.error_message)[:500])

    if snapshot.status.is_active and snapshot.thinking_text:
        peek = redact_untrusted(snapshot.thinking_text.strip())[-220:]
        if peek:
            lines.append("### Thinking")
            lines.append(peek)

    tools = list(snapshot.tools[-12:])
    if tools:
        lines.append("### Activity")
        lines.extend(_coalesce_tools(tools))

    if snapshot.status.is_active and snapshot.assistant_text:
        peek = redact_untrusted(snapshot.assistant_text.strip())[-200:]
        if peek:
            lines.append("")
            lines.append(f"_Draft…_ {peek}")

    if skipped_images:
        lines.append("")
        lines.append("### Images")
        for note in skipped_images[:5]:
            lines.append(f"- {redact_untrusted(note)[:160]}")

    if snapshot.degraded:
        lines.append("_Activity updates degraded; some edits may have failed._")

    if not lines:
        if snapshot.status.is_terminal:
            lines.append("_done_")
        else:
            lines.append(THREAD_THINKING_INDICATOR)

    text = "\n".join(lines).strip()
    text, _ = truncate_message(text, limit=limit)
    return _normalize_headings(text)[:limit]


def render_thread_final(
    snapshot: RunSnapshot,
    *,
    agent_name: str | None = None,
    skipped_images: list[str] | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Frozen final answer/error only — no Finished/Agent/Run/Git/Duration chrome."""
    del agent_name  # unused — kept for call-site compatibility

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        text = "### Error\n" + redact_untrusted(snapshot.error_message)[:1500]
        text, _ = truncate_message(text, limit=limit)
        return _normalize_headings(text)[:limit]

    body = snapshot.result_text or snapshot.assistant_text
    if not body:
        return "_No output._"

    text = redact_untrusted(body)
    if skipped_images:
        notes = "\n".join(
            f"- {redact_untrusted(note)[:160]}" for note in skipped_images[:5]
        )
        text = f"{text}\n\n_Images skipped:_\n{notes}"

    text, truncated = truncate_message(text, limit=limit)
    if truncated and "…(truncated)" not in text:
        text = text.rstrip() + "\n…(truncated)"
        text, _ = truncate_message(text, limit=limit)
    return _normalize_headings(text)[:limit]
