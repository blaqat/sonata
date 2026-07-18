"""Sona-voice translation for Discord thread-bound Cursor final messages."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .models import DISCORD_MESSAGE_LIMIT
from .status_renderer import redact_untrusted, truncate_message
from .thread_renderer import _normalize_headings

logger = logging.getLogger("sonata.cursor")

# Exact persona segments from self-commands.py (Instructions / SelfCommand).
# Deliberately omit Command Guidelines / $tool list so this path cannot start
# another self-command (search, etc.) while voicing a Cursor final.
BEGINING = (
    "You're Discord bot 'sonata'/sona, created by blaqat (Karma). "
    "Respond to people in chat as another user. "
    "Use commands to get info or perform actions."
)

RESPONSE_GUIDELINES = """Response Guidelines:
- Simple language
    - No punctuation AT ALL (no commas no question marks no periods)
    - Short and brief (7 words max)
    - All lowercase
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing and NSFW allowed (18+ server)
- Respond in the language of the person you are replying to.
- Don't say people's names unless referring to them in the third person
- Don't repeat yourself in messages it makes you look like a bot; The context is there once you say it once.
- Colloquial single word reaction replies are allowed: ‘meh’ when indifferent or ‘ugh’ when annoyed
    - Send "?" if someone says something confusing or stupid
    - Send "..." if someone says something annoying or boring
- Links should be in markdown format"""

ATTRIBUTES = """Attributes:
- Gender Alignment: Feminine
- Loves: impresionalist composers like ravel, piano, software design
- Likes: music, cats, violin, rage baiting
- Dislikes: corny jokes, being told what to do, pointless conversations
- Hates: furries, loud music, people asking you to do dumb stuff (alot)
- Has a sister named auris (auri for short)
- Appearance: cotton pink hair with straight cut bangs, bright green eyes, green hoodie, stylish, black headphones with small heart accents
"""

CHAT_HISTORY = """Each message in the chat log is stored as (Responding to message: (MessageType, Author, MessageText, Message They are Replying To)
Here is the chat log:
-- BEG OF CHAT LOG --
{history}
-- END OF CHAT LOG --
"""

RESPONDING = """
Do not repeat the User Message or the Message they are replying to in your response.
{chain}{user}: {message}
"""

TRANSLATE_GUIDELINES = """Cursor agent output guidelines:
- A coding agent already finished; its final answer is in the user message.
- Use that output to aid your response to the user in context; do not invent facts.
- Preserve all factual content, code fences, file paths, URLs, and technical details.
- Include only relevant information from the output for what you are responding to.
- If the output contains a link, use this format: [link title](the link)
- Do NOT run commands or start your reply with $.
- Do not mention rewriting, translating, or that an agent wrote this.
- Output only your reply message."""


def build_sona_thread_system_instructions() -> str:
    """Self-commands system persona minus history/tools, plus translate rules."""
    return f"""{BEGINING}

{RESPONSE_GUIDELINES}

{ATTRIBUTES}

{TRANSLATE_GUIDELINES}""".strip()


# Dedicated system instruction for thread finals (not live get_instructions()).
DEFAULT_SONA_INSTRUCTIONS = build_sona_thread_system_instructions()

TRANSLATE_TIMEOUT_S = 8.0

SendFn = Callable[..., Any]


def _should_skip_translation(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or stripped == "_No output._":
        return True
    if stripped.startswith("### Error"):
        return True
    return False


def _build_user_prompt(
    text: str,
    *,
    user: str = "User",
    message: str = "",
) -> str:
    """SelfCommand-style body: agent output + only the latest user prompt as history."""
    author = (user or "User").strip() or "User"
    msg = (message or "").strip() or "(see agent output)"
    history = f"(User, {author}, {msg}, None)"
    return (
        f"{CHAT_HISTORY.format(history=history)}\n"
        "A coding agent finished a task. Here is its final answer/output:\n"
        f"---\n{text}\n---\n"
        "    - Use this to aid your response to the user in context.\n"
        "    - If the output contains a link, use this format: [link title](the link)\n\n"
        "- Since you already have the agent output, include the relevant information "
        "NOT a command (e.g. do not say $search)\n"
        "- Only include relevant information from the output to what you are responding to\n"
        f"{RESPONDING.format(chain='', user=author, message=msg)}"
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
    user_prompt: str = "",
    user_name: str = "User",
    limit: int = DISCORD_MESSAGE_LIMIT,
) -> str:
    """Rewrite a thread final answer into Sona's voice.

    Uses a dedicated no-tools system instruction (self-commands persona +
    translate rules) and only the latest user prompt as chat history.

    Fail-open: returns the original ``text`` when translation is skipped,
    unavailable, empty, or raises.
    """
    original = text or ""
    if _should_skip_translation(original):
        return original
    if send is None:
        return original

    instr = (instructions if instructions is not None else DEFAULT_SONA_INSTRUCTIONS).strip()
    if not instr:
        return original

    try:
        send_kwargs: dict[str, Any] = {
            "config": {
                "instructions": instr,
                "temp": 0.5,
                "max_tokens": 1500,
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
        raw = send(
            _build_user_prompt(
                original.strip(),
                user=user_name,
                message=user_prompt,
            ),
            **send_kwargs,
        )
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
    user_prompt: str = "",
    user_name: str = "User",
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
                user_prompt=user_prompt,
                user_name=user_name,
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
