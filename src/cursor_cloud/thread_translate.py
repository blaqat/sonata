"""Sona-voice translation for Discord thread-bound Cursor final messages."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .models import DISCORD_MESSAGE_LIMIT
from .status_renderer import redact_untrusted, truncate_message
from .thread_renderer import _normalize_headings

logger = logging.getLogger("sonata.cursor")

# Mirrors Sonata's default chat persona (index.PROMPT) so translation stays
# available even when PromptManager instructions are not loaded (e.g. unit tests).
DEFAULT_SONA_INSTRUCTIONS = """
As "sonata", a Discord bot created by blaqat and :sparkles:"powered by AI":sparkles:™️, your role is to engage with users.
- You are a general expert on most subjects including math, coding, doctor, etc.
- Adopt a friendly and normal tone.
- Keep responses brief, possibly with a touch of humor.
- Only provide the response message without additional text or quote symbols.
- Respond in the language of the person you are replying to.
""".strip()

TRANSLATE_TIMEOUT_S = 8.0

SendFn = Callable[..., Any]


def _should_skip_translation(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or stripped == "_No output._":
        return True
    if stripped.startswith("### Error"):
        return True
    return False


def _build_user_prompt(text: str) -> str:
    return (
        "Rewrite the following coding-agent final answer in your normal Discord chat voice.\n"
        "Preserve all factual content, code fences, file paths, URLs, and technical details.\n"
        "Keep Discord-friendly length. Do not mention that you rewrote anything.\n"
        "Output only the rewritten message.\n\n"
        f"---\n{text}"
    )


def _sanitize_translated(text: str, *, limit: int = DISCORD_MESSAGE_LIMIT) -> str:
    cleaned = redact_untrusted(text)
    cleaned, truncated = truncate_message(cleaned, limit=limit)
    if truncated and "…(truncated)" not in cleaned:
        cleaned = cleaned.rstrip() + "\n…(truncated)"
        cleaned, _ = truncate_message(cleaned, limit=limit)
    return _normalize_headings(cleaned)[:limit]


def translate_thread_final_for_sona(
    text: str,
    *,
    send: SendFn | None = None,
    instructions: str | None = None,
    ai: str | None = None,
    model: str | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Rewrite a thread final answer into Sona's voice.

    Uses the runtime chat AI (``ai``) and that provider's configured model when
    ``model`` is omitted — same resolution path as normal Sona chat replies.

    Fail-open: returns the original ``text`` when translation is skipped,
    unavailable, empty, or raises.
    """
    original = text or ""
    if _should_skip_translation(original):
        return original
    if send is None:
        return original

    instr = (instructions or DEFAULT_SONA_INSTRUCTIONS).strip()
    if not instr:
        return original

    try:
        send_kwargs: dict[str, Any] = {
            "config": {
                "instructions": instr,
                "temp": 0.5,
                "max_tokens": 1500,
            },
        }
        if ai is not None:
            send_kwargs["AI"] = ai
        # Omit model unless explicitly set so PromptManager uses the AI type's
        # runtime-configured model (matches chat.request behavior).
        if model is not None:
            send_kwargs["model"] = model
        raw = send(_build_user_prompt(original.strip()), **send_kwargs)
        rewritten = str(raw or "").strip()
        if not rewritten:
            return original
        return _sanitize_translated(rewritten, limit=limit)
    except Exception:
        logger.debug(
            "Sona translation for thread final failed; using original text",
            exc_info=True,
        )
        return original


async def atranslate_thread_final_for_sona(
    text: str,
    *,
    send: SendFn | None = None,
    instructions: str | None = None,
    ai: str | None = None,
    model: str | None = None,
    timeout: float = TRANSLATE_TIMEOUT_S,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Async wrapper with timeout; always fail-open to the original text."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                translate_thread_final_for_sona,
                text,
                send=send,
                instructions=instructions,
                ai=ai,
                model=model,
                limit=limit,
            ),
            timeout=timeout,
        )
    except Exception:
        logger.debug(
            "Sona translation for thread final timed out/failed; using original",
            exc_info=True,
        )
        return text
