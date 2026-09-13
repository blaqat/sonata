"""Generic translation for Discord thread-bound Cursor final messages.

Persona / voice instructions and prompt shaping belong to the host adapter
(e.g. Sonata plugin). This module only: skip-check, send with injected
instructions, sanitize, and fail-open.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .models import DISCORD_MESSAGE_LIMIT
from .status_renderer import (
    _boundary_at_or_before,
    normalize_headings,
    redact_untrusted,
)


logger = logging.getLogger("sonata.cursor")

TRANSLATE_TIMEOUT_S = 8.0

SendFn = Callable[..., Any]


def _should_skip_translation(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or stripped == "_No output._":
        return True
    if stripped.startswith("### Error"):
        return True
    return False


def _sanitize_translated(text: str, *, limit: int = DISCORD_MESSAGE_LIMIT) -> str:
    """Sanitize translated finals; allow up to two Discord messages worth."""
    cleaned = normalize_headings(redact_untrusted(text))
    max_len = max(limit, limit * 2)
    if len(cleaned) <= max_len:
        return cleaned
    cut = _boundary_at_or_before(cleaned, max_len, min_keep=max(24, max_len // 4))
    if cut < max(24, max_len // 4):
        cut = max_len
    return cleaned[:cut].rstrip()


def translate_final(
    text: str,
    *,
    send: SendFn | None = None,
    instructions: str | None = None,
    prompt: str | None = None,
    ai: str | None = None,
    model: str | None = None,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Rewrite a thread final answer via an injected LLM ``send`` callable.

    ``instructions`` must be supplied by the host (persona / system prompt).
    ``prompt`` is the user-message body passed to ``send``; when omitted, the
    stripped original ``text`` is sent.

    Fail-open: returns the original ``text`` when translation is skipped,
    unavailable, empty, or raises.
    """
    original = text or ""
    if _should_skip_translation(original):
        return original
    if send is None:
        return original

    instr = (instructions or "").strip()
    if not instr:
        return original

    try:
        send_kwargs: dict[str, Any] = {
            "config": {
                "instructions": instr,
                "temp": 0.5,
                "max_tokens": 2000,
                # Prevent self-commands agent / $tool loops on this path.
                "agent": False,
            },
        }
        if ai is not None:
            send_kwargs["AI"] = ai
        # Omit model unless explicitly set so PromptManager uses the AI type's
        # runtime-configured model (matches chat.request behavior).
        if model is not None:
            send_kwargs["model"] = model
        body = prompt if prompt is not None else original.strip()
        raw = send(body, **send_kwargs)
        rewritten = str(raw or "").strip()
        if not rewritten:
            return original
        return _sanitize_translated(rewritten, limit=limit)
    except Exception:
        logger.debug(
            "Thread-final translation failed; using original text",
            exc_info=True,
        )
        return original


async def atranslate_final(
    text: str,
    *,
    send: SendFn | None = None,
    instructions: str | None = None,
    prompt: str | None = None,
    ai: str | None = None,
    model: str | None = None,
    timeout: float = TRANSLATE_TIMEOUT_S,
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Async wrapper with timeout; always fail-open to the original text."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                translate_final,
                text,
                send=send,
                instructions=instructions,
                prompt=prompt,
                ai=ai,
                model=model,
                limit=limit,
            ),
            timeout=timeout,
        )
    except Exception:
        logger.debug(
            "Thread-final translation timed out/failed; using original",
            exc_info=True,
        )
        return text
