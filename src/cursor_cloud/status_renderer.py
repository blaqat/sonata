"""Discord-safe H3 status rendering with hard length limits."""

from __future__ import annotations

import re
from typing import Any

from .models import DISCORD_MESSAGE_LIMIT, RunSnapshot, RunStatus


_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MENTION_RE = re.compile(r"@(everyone|here)|<@!?&?\d+>")


def redact_untrusted(text: str) -> str:
    text = text or ""
    text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    text = _MENTION_RE.sub(lambda m: m.group(0).replace("@", "@\u200b"), text)
    # Downgrade any markdown headings to plain text / H3-safe content.
    text = _HEADING_RE.sub("", text)
    return text


def normalize_headings(text: str) -> str:
    """Upgrade lone `#` / `##` lines to `###` so Discord never gets H1/H2."""
    text = re.sub(r"^##(?!#)\s*", "### ", text, flags=re.MULTILINE)
    text = re.sub(r"^#(?!#)\s*", "### ", text, flags=re.MULTILINE)
    return text


def _status_title(status: RunStatus) -> str:
    mapping = {
        RunStatus.QUEUED: "Queued",
        RunStatus.CREATING: "Creating",
        RunStatus.RUNNING: "Running",
        RunStatus.FINISHED: "Finished",
        RunStatus.ERROR: "Error",
        RunStatus.CANCELLED: "Cancelled",
        RunStatus.EXPIRED: "Expired",
    }
    return mapping.get(status, status.value.title())


def render_status(
    snapshot: RunSnapshot,
    *,
    agent_name: str | None = None,
    skipped_images: list[str] | None = None,
    extra_lines: list[str] | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Render a single Discord message body (H3 headings only, <= limit)."""
    lines: list[str] = [f"### {_status_title(snapshot.status)}"]
    if agent_name:
        lines.append(f"Agent: `{redact_untrusted(agent_name)[:80]}`")
    lines.append(f"Run: `{snapshot.run_id}`")

    if snapshot.error_message and snapshot.status == RunStatus.ERROR:
        lines.append("")
        lines.append("### Error")
        lines.append(redact_untrusted(snapshot.error_message)[:500])

    # Short thinking peek while active (full trail lives in /cursor history).
    if snapshot.status.is_active and snapshot.thinking_text:
        peek = redact_untrusted(snapshot.thinking_text.strip())[-160:]
        if peek:
            lines.append("")
            lines.append(f"_Thinking…_ {peek}")

    tools = snapshot.tools[-3:]
    if tools:
        lines.append("")
        lines.append("### Tools")
        for tool in tools:
            summary = redact_untrusted(tool.summary or tool.name)[:120]
            lines.append(f"- `{tool.name}` ({tool.status}) {summary}".rstrip())

    body = snapshot.result_text or (
        snapshot.assistant_text if snapshot.status.is_terminal else ""
    )
    if not body and snapshot.status.is_active and snapshot.assistant_text:
        body = snapshot.assistant_text[-400:]
    if body:
        lines.append("")
        lines.append("### Output")
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

    if extra_lines:
        for line in extra_lines:
            lines.append(redact_untrusted(line))

    if snapshot.degraded:
        lines.append("_Status updates degraded; some edits may have failed._")

    text = "\n".join(lines).strip()
    text, truncated = truncate_message(text, limit=limit)
    if truncated:
        # Ensure marker present
        if "…(truncated)" not in text:
            text = text.rstrip() + "\n…(truncated)"
            text, _ = truncate_message(text, limit=limit)
    # Final safety: never emit # or ## headings
    return normalize_headings(text)[:limit]


def truncate_message(text: str, *, limit: int = DISCORD_MESSAGE_LIMIT) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    # Prefer dropping older tool lines and trimming output section.
    marker = "\n…(truncated)"
    budget = max(0, limit - len(marker))
    sections = text.split("\n### ")
    if len(sections) <= 1:
        return text[:budget] + marker, True

    # Keep header + error; shrink tools/output from the middle/end.
    rebuilt = [sections[0]]
    for part in sections[1:]:
        rebuilt.append("### " + part)
    # Drop tool history first (index-based; avoid list.index O(n²)/duplicate bugs).
    filtered: list[str] = []
    for i, block in enumerate(rebuilt):
        rest = rebuilt[i + 1 :]
        if block.startswith("### Tools") and len("\n".join(filtered + rest)) > budget:
            continue
        filtered.append(block)
        joined = "\n".join(filtered)
        if len(joined) > budget:
            prefix = "\n".join(filtered[:-1])
            # Reserve one char for the joining newline when a prefix exists.
            overhead = 1 if prefix else 0
            filtered[-1] = filtered[-1][: max(0, budget - len(prefix) - overhead)]
            break
    out = "\n".join(filtered)
    if len(out) > budget:
        out = out[:budget]
    return out + marker, True


def initial_queued_message(*, run_hint: str | None = None) -> str:
    lines = ["### Queued", "Submitting Cursor Cloud Agent run…"]
    if run_hint:
        lines.append(redact_untrusted(run_hint)[:200])
    return "\n".join(lines)[:DISCORD_MESSAGE_LIMIT]


def safe_tool_summary(name: str, args: Any, result: Any, *, truncated: dict | None = None) -> str:
    """Never render raw tool args/results that might contain secrets."""
    parts = [name]
    if truncated:
        if truncated.get("args"):
            parts.append("args=truncated")
        if truncated.get("result"):
            parts.append("result=truncated")
    # Only include shallow keys, not values.
    if isinstance(args, dict):
        keys = sorted(str(k) for k in args.keys())[:6]
        if keys:
            parts.append("keys=" + ",".join(keys))
    return redact_untrusted(" ".join(parts))[:160]
