"""Discord-safe H3 status rendering with hard length limits."""

from __future__ import annotations

import re
from typing import Any

from .models import DISCORD_MESSAGE_LIMIT, RunSnapshot, RunStatus


_HEADING_RE = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_MENTION_RE = re.compile(r"@(everyone|here)|<@!?&?\d+>")

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
    "read_file": "read",
    "run_terminal_cmd": "shell",
}

# Cursor SSE uses public name ``mcp``; identity often lives in args.
# Prefer explicit MCP identity keys; keep a short fallback list for CallMcpTool.
_MCP_TOOL_NAME_KEYS = (
    "toolName",
    "tool_name",
    "providerToolName",
    "mcpToolName",
    "name",
)
_MCP_SERVER_NAME_KEYS = (
    "serverName",
    "server_name",
    "mcpServerName",
    "server",
)


def _slug_tool_token(value: str) -> str:
    text = redact_untrusted(str(value or "")).strip().lower()
    text = re.sub(r"[^a-z0-9:_+-]+", "-", text)
    return text.strip("-_:")[:48]


def _mcp_tool_identity(args: Any) -> tuple[str | None, str | None]:
    """Return (server, tool) labels from an MCP tool_call args object."""
    if not isinstance(args, dict):
        return None, None
    tool: str | None = None
    server: str | None = None
    for key in _MCP_TOOL_NAME_KEYS:
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            tool = raw.strip()
            break
        if isinstance(raw, dict):
            for nested_key in ("name", "toolName", "tool_name"):
                nested = raw.get(nested_key)
                if isinstance(nested, str) and nested.strip():
                    tool = nested.strip()
                    break
            if tool:
                break
    for key in _MCP_SERVER_NAME_KEYS:
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            server = raw.strip()
            break
    return server, tool


def tool_family(name: str, args: Any = None) -> str:
    """Map a tool name (+ optional args) to a coalesced summary family.

    MCP tool calls often arrive as ``name="mcp"`` with the real tool in args, or
    as ``mcp__provider__tool``. Both must count under an ``mcp…`` family rather
    than being dropped or collapsed into an opaque token.
    """
    text = str(name or "tool").strip()
    if not text:
        return "tool"
    if text in _TOOL_FAMILY_ALIASES:
        return _TOOL_FAMILY_ALIASES[text]

    lower = text.lower()
    if lower.startswith("mcp__"):
        parts = [p for p in text.split("__") if p]
        if len(parts) >= 3:
            tool = _slug_tool_token(parts[-1])
            if tool:
                return f"mcp:{tool}"
        return "mcp"
    if lower in {"mcp", "callmcptool"} or lower.startswith("mcp:"):
        server, tool = _mcp_tool_identity(args)
        tool_slug = _slug_tool_token(tool or "")
        if tool_slug:
            # Prefer tool identity (search/fetch); server is often a long plugin id.
            return f"mcp:{tool_slug}"
        server_slug = _slug_tool_token(server or "")
        if server_slug:
            return f"mcp:{server_slug}"
        if lower.startswith("mcp:") and len(lower) > 4:
            slug = _slug_tool_token(lower[4:])
            return f"mcp:{slug}" if slug else "mcp"
        return "mcp"

    base = text.split("_")[0].lower()
    return _TOOL_FAMILY_ALIASES.get(base, base or "tool")


def redact_untrusted(text: str) -> str:
    text = text or ""
    text = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
    text = _MENTION_RE.sub(lambda m: m.group(0).replace("@", "@\u200b"), text)
    # Downgrade any markdown headings to plain text / H3-safe content.
    text = _HEADING_RE.sub("", text)
    return text


# Sentence / paragraph breaks for live peeks (prefer not cutting mid-thought).
_SENTENCE_BREAK_RE = re.compile(r'[.!?…]["\')\]]*(?:\s+|$)|\n+')


def _boundary_at_or_before(text: str, index: int, *, min_keep: int) -> int:
    """Snap ``index`` left to the end of a sentence/paragraph when possible."""
    if index <= 0:
        return 0
    if index >= len(text):
        return len(text)
    window = text[:index]
    best = -1
    for match in _SENTENCE_BREAK_RE.finditer(window):
        end = match.end()
        if end >= min_keep:
            best = end
    if best >= min_keep:
        return best
    space = window.rfind(" ")
    if space >= min_keep:
        return space
    return index


def _boundary_at_or_after(text: str, index: int, *, min_keep: int) -> int:
    """Snap ``index`` right to the start of the next sentence/paragraph when possible."""
    if index <= 0:
        return 0
    if index >= len(text):
        return len(text)
    window = text[index:]
    for match in _SENTENCE_BREAK_RE.finditer(window):
        start = index + match.end()
        if len(text) - start >= min_keep:
            return start
    space = window.find(" ")
    if space != -1:
        start = index + space + 1
        if len(text) - start >= min_keep:
            return start
    return index


def format_live_peek(
    text: str,
    *,
    head_chars: int = 140,
    tail_chars: int = 260,
) -> str:
    """Live thinking/draft peek: sentence-aware head + tail with an ellipsis.

    Short buffers are returned in full. Longer ones keep the opening thesis and
    the latest continuation, preferring sentence/paragraph boundaries over raw
    character cuts so Discord peeks stay readable mid-stream.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= head_chars + tail_chars:
        return cleaned

    head_end = _boundary_at_or_before(
        cleaned, head_chars, min_keep=max(24, head_chars // 3)
    )
    tail_start = _boundary_at_or_after(
        cleaned,
        len(cleaned) - tail_chars,
        min_keep=max(24, tail_chars // 3),
    )
    if tail_start <= head_end:
        # Overlap / no clean split — fall back to a sentence-aware tail window.
        start = _boundary_at_or_after(
            cleaned,
            max(0, len(cleaned) - (head_chars + tail_chars)),
            min_keep=max(24, (head_chars + tail_chars) // 3),
        )
        return cleaned[start:].lstrip()

    head = cleaned[:head_end].rstrip()
    tail = cleaned[tail_start:].lstrip()
    if not head:
        return tail
    if not tail:
        return head
    return f"{head}\n…\n{tail}"


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
        peek = format_live_peek(
            redact_untrusted(snapshot.thinking_text),
            head_chars=100,
            tail_chars=180,
        )
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


def split_discord_messages(
    text: str,
    *,
    limit: int = DISCORD_MESSAGE_LIMIT,
    max_parts: int = 2,
) -> list[str]:
    """Split oversized Discord content into at most ``max_parts`` messages.

    Breaks near ``limit`` on sentence/paragraph boundaries when possible so a
    long final answer becomes two posts instead of a single truncated one.
    Any remainder beyond ``max_parts * limit`` is dropped from the last part
    with a truncation marker (hard Discord ceiling).
    """
    cleaned = text if text is not None else ""
    if not cleaned:
        return [cleaned]
    parts: list[str] = []
    remaining = cleaned
    parts_left = max(1, int(max_parts))
    while remaining and parts_left > 1:
        if len(remaining) <= limit:
            parts.append(remaining)
            return parts
        break_at = _boundary_at_or_before(
            remaining, limit, min_keep=max(24, limit // 4)
        )
        if break_at < max(24, limit // 4):
            break_at = limit
        chunk = remaining[:break_at].rstrip()
        if not chunk:
            chunk = remaining[:limit]
            break_at = len(chunk)
        parts.append(chunk)
        remaining = remaining[break_at:].lstrip()
        parts_left -= 1
    if remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
        else:
            trimmed, _ = truncate_message(remaining, limit=limit)
            parts.append(trimmed)
    return parts or [""]


def initial_queued_message(*, run_hint: str | None = None) -> str:
    lines = ["### Queued", "Submitting Cursor Cloud Agent run…"]
    if run_hint:
        lines.append(redact_untrusted(run_hint)[:200])
    return "\n".join(lines)[:DISCORD_MESSAGE_LIMIT]


def safe_tool_summary(name: str, args: Any, result: Any, *, truncated: dict | None = None) -> str:
    """Never render raw tool args/results that might contain secrets."""
    del result  # never render raw tool results
    parts = [name]
    if truncated:
        if truncated.get("args"):
            parts.append("args=truncated")
        if truncated.get("result"):
            parts.append("result=truncated")
    # Only include shallow keys, not values — except MCP tool identity labels.
    if isinstance(args, dict):
        keys = sorted(str(k) for k in args.keys())[:6]
        if keys:
            parts.append("keys=" + ",".join(keys))
        lower = str(name or "").strip().lower()
        if lower in {"mcp", "callmcptool"} or lower.startswith("mcp"):
            server, tool = _mcp_tool_identity(args)
            if tool:
                parts.append(f"tool={_slug_tool_token(tool)}")
            if server:
                parts.append(f"server={_slug_tool_token(server)}")
    return redact_untrusted(" ".join(parts))[:160]
