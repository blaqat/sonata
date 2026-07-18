"""Discord thread chat-room rendering (activity vs final messages)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .models import DISCORD_MESSAGE_LIMIT, RunSnapshot, RunStatus, ToolActivity
from .status_renderer import (
    _status_title,
    redact_untrusted,
    truncate_message,
)

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


def render_thread_activity(
    snapshot: RunSnapshot,
    *,
    agent_name: str | None = None,
    skipped_images: list[str] | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Single editable in-flight Activity message body."""
    lines: list[str] = [f"### {_status_title(snapshot.status)}"]
    if agent_name:
        lines.append(f"Agent: `{redact_untrusted(agent_name)[:80]}`")
    lines.append(f"Run: `{snapshot.run_id}`")

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        lines.append("")
        lines.append("### Error")
        lines.append(redact_untrusted(snapshot.error_message)[:500])

    if snapshot.status.is_active and snapshot.thinking_text:
        peek = redact_untrusted(snapshot.thinking_text.strip())[-160:]
        if peek:
            lines.append("")
            lines.append(f"_Thinking…_ {peek}")

    tools = list(snapshot.tools[-12:])
    if tools:
        lines.append("")
        lines.append("### Activity")
        lines.extend(_coalesce_tools(tools))

    if snapshot.status.is_active and snapshot.assistant_text:
        peek = redact_untrusted(snapshot.assistant_text.strip())[-200:]
        if peek:
            lines.append("")
            lines.append(f"_Draft…_ {peek}")

    if snapshot.status.is_terminal and not snapshot.error_message:
        lines.append("")
        lines.append("_Run complete — see result message below._")

    if skipped_images:
        lines.append("")
        lines.append("### Images")
        for note in skipped_images[:5]:
            lines.append(f"- {redact_untrusted(note)[:160]}")

    if snapshot.degraded:
        lines.append("_Activity updates degraded; some edits may have failed._")

    text = "\n".join(lines).strip()
    text, _ = truncate_message(text, limit=limit)
    text = re.sub(r"^##(?!#)\s*", "### ", text, flags=re.MULTILINE)
    text = re.sub(r"^#(?!#)\s*", "### ", text, flags=re.MULTILINE)
    return text[:limit]


def render_thread_final(
    snapshot: RunSnapshot,
    *,
    agent_name: str | None = None,
    skipped_images: list[str] | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Frozen final assistant result/error/git message."""
    title = _status_title(snapshot.status)
    lines: list[str] = [f"### {title}"]
    if agent_name:
        lines.append(f"Agent: `{redact_untrusted(agent_name)[:80]}`")
    lines.append(f"Run: `{snapshot.run_id}`")

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        lines.append("")
        lines.append(redact_untrusted(snapshot.error_message)[:1500])

    body = snapshot.result_text or snapshot.assistant_text
    if body:
        lines.append("")
        lines.append("### Result")
        lines.append(redact_untrusted(body))

    if snapshot.git_branches:
        lines.append("")
        lines.append("### Git")
        for branch in snapshot.git_branches[:3]:
            bit = branch.branch or "(branch)"
            if branch.pr_url:
                lines.append(f"- `{bit}` — {branch.pr_url}")
            else:
                lines.append(f"- `{bit}`")

    if snapshot.duration_ms is not None:
        seconds = snapshot.duration_ms / 1000.0
        lines.append(f"Duration: {seconds:.1f}s")

    if skipped_images:
        lines.append("")
        lines.append("### Images")
        for note in skipped_images[:5]:
            lines.append(f"- {redact_untrusted(note)[:160]}")

    text = "\n".join(lines).strip()
    text, truncated = truncate_message(text, limit=limit)
    if truncated and "…(truncated)" not in text:
        text = text.rstrip() + "\n…(truncated)"
        text, _ = truncate_message(text, limit=limit)
    text = re.sub(r"^##(?!#)\s*", "### ", text, flags=re.MULTILINE)
    text = re.sub(r"^#(?!#)\s*", "### ", text, flags=re.MULTILINE)
    return text[:limit]
