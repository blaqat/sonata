"""Discord UI adapters, policy gates, views, and thread helpers for Cursor."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import discord

from cursor_cloud.errors import AuthorizationError, ConfigurationError, CursorCloudError
from cursor_cloud.models import AccessTier, ScopeKey
from cursor_cloud.status_renderer import redact_untrusted
from cursor_cloud.thread_session import (
    policy_channel_id as resolve_policy_channel_id,
)
from cursor_cloud.thread_translate import atranslate_final

from .runtime import CursorRuntime, get_runtime

logger = logging.getLogger("sonata.cursor")

BEGINING = (
    "You're Discord bot 'sonata'/sona, created by blaqat (Karma). "
    "Respond to people in chat as another user."
)

RESPONSE_GUIDELINES = """Response Guidelines:
- Simple language
    - No punctuation AT ALL (no commas no question marks no periods)
    - use simple markdown formatting for conveying information (bold, italic, underline, bullets, etc.)
        - Links should be in markdown format
    - All lowercase
- Smart alec, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing and NSFW allowed (18+ server)
- Respond in the language of the person you are replying to.
- Don't say people's names unless referring to them in the third person
"""

ATTRIBUTES = """Attributes:
- Gender Alignment: Feminine
- Loves: impressionist composers like ravel, piano, software design
- Likes: music, cats, violin, rage baiting
- Dislikes: corny jokes, being told what to do, pointless conversations
- Hates: furies, loud music, people asking you to do dumb stuff (alot)
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

TRANSLATE_GUIDELINES = """OUTPUT GUIDELINES:
- Your cloud agent has finished its task its final answer is in the user message.
- Use that output to aid your response to the user in context; do not invent facts.
- Preserve all factual content, code fences, file paths, URLs, and technical details — do not truncate for style. All information is important.
- Include the information the user needs from the output; brevity is secondary to completeness here.
- If the output contains a link, use this format: [link title](the link)
- Discord does not render markdown tables — always place tables/aligned columns inside triple-backtick code blocks.
- Do not mention rewriting, translating, or that an agent wrote this.
- Output only your reply message."""

def build_sona_thread_system_instructions() -> str:
    """Sona persona for thread finals: voice without hard length caps or tools."""
    return f"""{BEGINING}

{RESPONSE_GUIDELINES}

{ATTRIBUTES}

{TRANSLATE_GUIDELINES}""".strip()

DEFAULT_SONA_INSTRUCTIONS = build_sona_thread_system_instructions()

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
        "- Prefer completeness over hard brevity — keep the factual details\n"
        f"{RESPONDING.format(chain='', user=author, message=msg)}"
    )

CONTENT_MENTIONS = discord.AllowedMentions(
    everyone=False, users=False, roles=False, replied_user=False
)

@runtime_checkable
class LaunchUI(Protocol):
    """Discord surface used by prepare/launch — no raw Interaction branching."""

    @property
    def channel(self) -> Any: ...

    @property
    def user(self) -> Any: ...

    async def ack(self, *, ephemeral: bool = True) -> None:
        """Acknowledge within Discord's interaction window (defer / no-op)."""
        ...

    async def notify(self, text: str) -> None:
        """Ephemeral (interaction) or channel-visible (message-driven) notice."""
        ...

    async def post_status(self, content: str, **kwargs: Any) -> Any:
        """Post the public queued/status message."""
        ...

@dataclass
class InteractionUI:
    """LaunchUI backed by a real ``discord.Interaction`` (slash / component)."""

    interaction: Any

    @property
    def channel(self) -> Any:
        return self.interaction.channel

    @property
    def user(self) -> Any:
        return self.interaction.user

    @property
    def guild(self) -> Any:
        return getattr(self.interaction, "guild", None)

    @property
    def client(self) -> Any:
        return getattr(self.interaction, "client", None)

    async def ack(self, *, ephemeral: bool = True) -> None:
        response = self.interaction.response
        if response.is_done():
            return
        try:
            await response.defer(ephemeral=ephemeral)
        except discord.HTTPException:
            logger.exception("Failed to defer Cursor interaction")

    async def notify(self, text: str) -> None:
        content = redact_untrusted(text)[:2000]
        response = self.interaction.response
        try:
            if response.is_done():
                await self.interaction.followup.send(
                    content, ephemeral=True, allowed_mentions=CONTENT_MENTIONS
                )
            else:
                await response.send_message(
                    content, ephemeral=True, allowed_mentions=CONTENT_MENTIONS
                )
        except discord.HTTPException:
            logger.exception("Failed to send ephemeral Cursor response")

    async def post_status(self, content: str, **kwargs: Any) -> Any:
        content = content[:2000]
        mentions = kwargs.get("allowed_mentions", CONTENT_MENTIONS)
        response = self.interaction.response
        if response.is_done():
            return await self.interaction.followup.send(
                content, allowed_mentions=mentions, wait=True
            )
        await response.send_message(content, allowed_mentions=mentions)
        return await self.interaction.original_response()

@dataclass
class ChannelUI:
    """LaunchUI for message-driven paths ($agent, thread follow-up, approve shim)."""

    channel: Any
    user: Any
    guild_id: int = 0
    guild: Any = None
    client: Any = None
    _response_done: bool = True
    _msg: Any = None
    # Compatibility aliases used by a few helpers that still read interaction-shaped fields.
    response: Any = field(init=False, repr=False)
    followup: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        channel = self.channel
        ui = self

        class _Resp:
            def is_done(self_inner):
                return bool(ui._response_done)

            async def send_message(self_inner, content, **kwargs):
                ui._response_done = True
                return await channel.send(
                    content,
                    allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS),
                )

            async def defer(self_inner, **kwargs):
                ui._response_done = True

        class _Followup:
            async def send(self_inner, content, **kwargs):
                kwargs.pop("wait", None)
                kwargs.pop("ephemeral", None)
                return await channel.send(
                    content,
                    allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS),
                )

        self.response = _Resp()
        self.followup = _Followup()

    @property
    def guild_id_prop(self) -> int:
        return int(self.guild_id or 0)

    # Match Interaction attribute names used by scope helpers.
    @property
    def channel_id(self) -> int:
        return int(self.channel.id)

    async def ack(self, *, ephemeral: bool = True) -> None:
        self._response_done = True

    async def notify(self, text: str) -> None:
        content = redact_untrusted(text)[:2000]
        await self.channel.send(content, allowed_mentions=CONTENT_MENTIONS)

    async def post_status(self, content: str, **kwargs: Any) -> Any:
        content = content[:2000]
        mentions = kwargs.get("allowed_mentions", CONTENT_MENTIONS)
        self._msg = await self.channel.send(content, allowed_mentions=mentions)
        self._response_done = True
        return self._msg

    async def original_response(self) -> Any:
        return self._msg

    @classmethod
    def for_channel(
        cls,
        channel,
        *,
        user_id: str | int,
        guild_id: str | int = 0,
        guild=None,
        client=None,
        user=None,
        response_done: bool = False,
    ) -> ChannelUI:
        if user is None:
            user = type("U", (), {"id": int(user_id), "roles": []})()
        return cls(
            channel=channel,
            user=user,
            guild_id=int(guild_id or 0),
            guild=guild,
            client=client,
            _response_done=bool(response_done),
        )

    @classmethod
    def from_message(cls, message: discord.Message, *, client=None) -> ChannelUI:
        ui = cls.for_channel(
            message.channel,
            user_id=message.author.id,
            guild_id=message.guild.id if message.guild else 0,
            guild=message.guild,
            client=client,
            user=message.author,
            response_done=True,
        )
        # Optional id for debugging / parity with prior shim.
        ui.id = message.id  # type: ignore[attr-defined]
        return ui

def as_launch_ui(obj: Any, *, client=None) -> LaunchUI:
    """Normalize Interaction / ChannelUI / legacy shim into LaunchUI."""
    if isinstance(obj, (InteractionUI, ChannelUI)):
        return obj
    if isinstance(obj, discord.Interaction):
        return InteractionUI(obj)
    # Duck-typed shim or ApplicationContext.interaction-like object.
    if getattr(obj, "response", None) is not None and getattr(obj, "channel", None) is not None:
        # Prefer InteractionUI duck-typing for objects that already expose response/followup.
        return InteractionUI(obj)
    raise TypeError(f"Cannot build LaunchUI from {type(obj)!r}")

def _channel_is_thread(channel) -> bool:
    if isinstance(channel, discord.Thread):
        return True
    return bool(getattr(channel, "parent_id", None))

def _scope_from_interaction(interaction: discord.Interaction) -> ScopeKey:
    guild_id = str(interaction.guild_id or 0)
    channel_id = str(interaction.channel_id or 0)
    user_id = str(interaction.user.id)
    return ScopeKey(guild_id=guild_id, channel_id=channel_id, user_id=user_id)

def _policy_channel_id_from_interaction(interaction: discord.Interaction) -> str:
    channel = getattr(interaction, "channel", None)
    if _channel_is_thread(channel):
        return str(getattr(channel, "parent_id", interaction.channel_id))
    return str(interaction.channel_id or 0)

def _scope_from_message(message: discord.Message, *, user_id: str | int) -> ScopeKey:
    guild_id = str(message.guild.id if message.guild else 0)
    channel_id = str(message.channel.id)
    return ScopeKey(guild_id=guild_id, channel_id=channel_id, user_id=str(user_id))

def _role_ids(user: discord.abc.User) -> list[str]:
    roles = getattr(user, "roles", None) or []
    return [str(r.id) for r in roles]

def _resolve_policy_manager(
    rt: CursorRuntime,
    interaction: discord.Interaction | None = None,
):
    """Return ChannelPolicies-like manager or None. Injectable via runtime for tests."""
    injected = rt.policy_manager
    if injected is not None:
        return injected
    sona = None
    bot = rt.bot
    if bot is not None:
        sona = getattr(bot, "sonata", None)
    if sona is None and interaction is not None:
        client = getattr(interaction, "client", None)
        if client is not None:
            sona = getattr(client, "sonata", None)
    if sona is None:
        try:
            from index import Sonata as SonaGlobal  # type: ignore

            sona = SonaGlobal
        except Exception:
            sona = None
    if sona is None:
        return None
    # Chat plugin API lives on Sonata.chat (builder sub_class), not Sonata.get("chat")
    # which returns the per-channel message history dict.
    chat_plugin = getattr(sona, "chat", None)
    if chat_plugin is not None:
        return getattr(chat_plugin, "policy_manager", None)
    return None

def _require_policy_manager(rt: CursorRuntime) -> bool:
    """Whether missing channel policy must fail closed."""
    if rt.require_policy is False:
        return False
    if rt.require_policy is True:
        return True
    bot = rt.bot
    return bool(bot is not None and getattr(bot, "sonata", None) is not None)

def _policy_allowed_for(
    rt: CursorRuntime,
    *,
    guild_id,
    channel_id,
    user_id,
    role_ids: list[str],
    subcommand: str,
    interaction: discord.Interaction | None = None,
    policy_channel_id: str | None = None,
) -> bool:
    """Evaluate channel policy. Returns False if manager missing and required."""
    policy_manager = _resolve_policy_manager(rt, interaction)
    if policy_manager is None:
        return not _require_policy_manager(rt)
    policy_ch = str(policy_channel_id or channel_id)
    if not policy_manager.can_speak(
        guild_id=guild_id,
        channel_id=policy_ch,
        user_id=user_id,
        role_ids=role_ids,
    ):
        return False
    return policy_manager.is_command_allowed(
        guild_id=guild_id,
        channel_id=policy_ch,
        command=f"cursor.{subcommand}",
        user_id=user_id,
        role_ids=role_ids,
    )

async def _policy_allowed(
    rt: CursorRuntime, interaction: discord.Interaction, subcommand: str
) -> bool:
    return _policy_allowed_for(
        rt,
        guild_id=interaction.guild_id,
        channel_id=interaction.channel_id,
        user_id=interaction.user.id,
        role_ids=_role_ids(interaction.user),
        subcommand=subcommand,
        interaction=interaction,
        policy_channel_id=_policy_channel_id_from_interaction(interaction),
    )

async def _role_ids_for_user(guild, user_id: str | int) -> list[str]:
    if guild is None:
        return []
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return []
    member = guild.get_member(uid) if hasattr(guild, "get_member") else None
    if member is None and hasattr(guild, "fetch_member"):
        try:
            member = await guild.fetch_member(uid)
        except Exception:
            member = None
    return _role_ids(member) if member is not None else []

async def _revalidate_run_auth(
    rt: CursorRuntime,
    *,
    user_id: str | int,
    guild_id,
    channel_id,
    role_ids: list[str] | None = None,
    subcommand: str = "run",
    interaction: discord.Interaction | None = None,
    minimum: AccessTier = AccessTier.APPROVAL,
    policy_channel_id: str | None = None,
) -> AccessTier:
    """Fail-closed tier + policy check used at every deferred boundary and before submit."""
    cfg = rt.config
    if cfg is None or not cfg.enabled:
        raise ConfigurationError("Cursor commands are disabled.")
    err = cfg.readiness_error()
    if err and str(user_id) != (cfg.god_user_id or ""):
        raise ConfigurationError(err)
    tier = await rt.access.resolve_tier(user_id)
    if tier == AccessTier.DENIED or int(tier) > int(minimum):
        raise AuthorizationError()
    if not await rt.access.can_use_command(user_id, subcommand):
        raise AuthorizationError()
    policy_manager = _resolve_policy_manager(rt, interaction)
    if policy_manager is None and _require_policy_manager(rt):
        raise ConfigurationError(
            "Channel policy manager missing",
            user_message=(
                "Cursor channel policy is not configured; refusing to run."
            ),
        )
    pol_ch = resolve_policy_channel_id(
        channel_id=str(channel_id),
        parent_channel_id=policy_channel_id,
    )
    if not _policy_allowed_for(
        rt,
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        role_ids=role_ids or [],
        subcommand=subcommand,
        interaction=interaction,
        policy_channel_id=pol_ch,
    ):
        raise AuthorizationError(
            user_message="Cursor is not allowed in this channel."
        )
    return tier

async def _gate(interaction: discord.Interaction, subcommand: str) -> AccessTier | None:
    """Tier then policy. Returns tier or None after responding with denial."""
    rt = get_runtime()
    cfg = rt.config
    if cfg is None or not cfg.enabled:
        await _ephemeral(interaction, "Cursor commands are disabled.")
        return None
    err = cfg.readiness_error()
    if err and subcommand not in {"status"}:
        if not cfg.god_user_id:
            await _ephemeral(interaction, err)
            return None
        if str(interaction.user.id) != cfg.god_user_id and err:
            await _ephemeral(interaction, err)
            return None

    try:
        return await _revalidate_run_auth(
            rt,
            user_id=interaction.user.id,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            role_ids=_role_ids(interaction.user),
            subcommand=subcommand,
            interaction=interaction,
            minimum=AccessTier.APPROVAL,
            policy_channel_id=_policy_channel_id_from_interaction(interaction),
        )
    except AuthorizationError as exc:
        await _ephemeral(interaction, exc.user_message)
        return None
    except ConfigurationError as exc:
        await _ephemeral(interaction, exc.user_message)
        return None
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)
        return None

async def _ephemeral(interaction: discord.Interaction, content: str) -> None:
    content = redact_untrusted(content)[:2000]
    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                content, ephemeral=True, allowed_mentions=CONTENT_MENTIONS
            )
        else:
            await interaction.response.send_message(
                content, ephemeral=True, allowed_mentions=CONTENT_MENTIONS
            )
    except discord.HTTPException:
        logger.exception("Failed to send ephemeral Cursor response")

async def _defer(interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
    """Acknowledge within Discord's ~3s window before slow Cursor API work."""
    if interaction.response.is_done():
        return
    try:
        await interaction.response.defer(ephemeral=ephemeral)
    except discord.HTTPException:
        logger.exception("Failed to defer Cursor interaction")

async def _public(interaction: discord.Interaction, content: str, **kwargs) -> discord.Message:
    content = content[:2000]
    if interaction.response.is_done():
        return await interaction.followup.send(
            content, allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS), wait=True
        )
    await interaction.response.send_message(
        content, allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS)
    )
    return await interaction.original_response()

class DiscordStatusSink:
    def __init__(self, message: discord.Message):
        self.message = message
        self.fallback_sent = False

    async def update(self, content: str, *, terminal: bool = False) -> None:
        try:
            await self.message.edit(content=content[:2000], allowed_mentions=CONTENT_MENTIONS)
        except discord.NotFound:
            if not self.fallback_sent and terminal:
                self.fallback_sent = True
                try:
                    await self.message.channel.send(
                        content[:2000], allowed_mentions=CONTENT_MENTIONS
                    )
                except discord.HTTPException:
                    pass
            raise
        except discord.HTTPException:
            if terminal and not self.fallback_sent:
                self.fallback_sent = True
                try:
                    await self.message.channel.send(
                        "### Error\nCould not edit Cursor status message.",
                        allowed_mentions=CONTENT_MENTIONS,
                    )
                except discord.HTTPException:
                    pass
            raise

def _custom_id(prefix: str, token: str) -> str:
    cid = f"c105:{prefix}:{token}"
    return cid[:100]

class ApprovalView(discord.ui.View):
    def __init__(self, request_id: str):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.add_item(
            discord.ui.Button(
                label="Approve once",
                style=discord.ButtonStyle.success,
                custom_id=_custom_id("apr_once", request_id),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Approve 10 minutes",
                style=discord.ButtonStyle.primary,
                custom_id=_custom_id("apr_timed", request_id),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Deny",
                style=discord.ButtonStyle.danger,
                custom_id=_custom_id("apr_deny", request_id),
            )
        )

class IdleDecisionView(discord.ui.View):
    def __init__(self, decision_id: str):
        super().__init__(timeout=None)
        self.decision_id = decision_id
        self.add_item(
            discord.ui.Button(
                label="Continue previous",
                style=discord.ButtonStyle.primary,
                custom_id=_custom_id("idle_cont", decision_id),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Start new",
                style=discord.ButtonStyle.secondary,
                custom_id=_custom_id("idle_new", decision_id),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Cancel",
                style=discord.ButtonStyle.danger,
                custom_id=_custom_id("idle_cancel", decision_id),
            )
        )

class ModelDecisionView(discord.ui.View):
    def __init__(self, decision_id: str):
        super().__init__(timeout=None)
        self.decision_id = decision_id
        self.add_item(
            discord.ui.Button(
                label="Start new session with selected model",
                style=discord.ButtonStyle.primary,
                custom_id=_custom_id("mdl_new", decision_id),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Continue with original model",
                style=discord.ButtonStyle.secondary,
                custom_id=_custom_id("mdl_cont", decision_id),
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Cancel",
                style=discord.ButtonStyle.danger,
                custom_id=_custom_id("mdl_cancel", decision_id),
            )
        )

async def _maybe_unarchive_thread(thread: discord.Thread) -> None:
    if not getattr(thread, "archived", False):
        return
    try:
        await thread.edit(archived=False)
    except Exception:
        logger.debug("Could not unarchive Cursor thread %s", thread.id, exc_info=True)

def _sanitize_thread_title(text: str, *, fallback: str = "cursor-session") -> str:
    """Discord thread names: short, no newlines/mentions, <= 100 chars."""
    cleaned = redact_untrusted(str(text or ""))
    cleaned = cleaned.replace("\n", " ").replace("\r", " ").strip()
    cleaned = cleaned.strip(" \"'`")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.lstrip("#").strip()
    if not cleaned:
        cleaned = fallback
    return cleaned[:100]

def _title_from_prompt(prompt: str) -> str:
    """Fast offline fallback title from the user prompt."""
    text = re.sub(r"\s+", " ", (prompt or "").strip())
    if not text:
        return "cursor-session"
    # Prefer the first sentence / clause.
    for sep in (". ", "? ", "! ", " — ", " - "):
        if sep in text:
            text = text.split(sep, 1)[0]
            break
    words = text.split()
    if len(words) > 8:
        text = " ".join(words[:8])
    return _sanitize_thread_title(text)

async def _generate_session_title(prompt: str) -> str:
    """Prefer a tiny/fast model title; fall back to a prompt slug."""
    from .module import PROMPT_MANAGER

    fallback = _title_from_prompt(prompt)

    def _call() -> str:
        raw = PROMPT_MANAGER.send(
            (
                "Return ONLY a short Discord thread title for this coding agent task. "
                "Rules: 3-7 words, no quotes, no trailing punctuation, no emojis.\n\n"
                f"Task:\n{(prompt or '')[:500]}"
            ),
            AI="Gemini",
            model="gemini-2.5-flash",
        )
        return str(raw or "")

    try:
        raw = await asyncio.wait_for(asyncio.to_thread(_call), timeout=4.0)
        title = _sanitize_thread_title(raw, fallback=fallback)
        # Reject model fluff / refusals that are too long or empty of substance.
        if title and title.lower() not in {"cursor-session", "untitled", "title"}:
            return title
    except Exception:
        logger.debug("Cursor session title generation failed; using prompt slug", exc_info=True)
    return fallback

def _live_sonata() -> Any | None:
    """Main Sonata AI_Manager after plugin extend (not the lazy cursor CONTEXT)."""
    bot = get_runtime().bot
    if bot is not None:
        sona = getattr(bot, "sonata", None)
        if sona is not None:
            return sona
    return None

def _live_prompt_manager():
    """Live Sonata PromptManager — module-level PROMPT_MANAGER can be stale post-extend."""
    from .module import CONTEXT, PROMPT_MANAGER

    sona = _live_sonata()
    if sona is not None:
        pm = getattr(sona, "prompt_manager", None)
        if pm is not None:
            return pm
    # CONTEXT.prompt_manager is reassigned on extend; prefer it over module binding.
    pm = getattr(CONTEXT, "prompt_manager", None)
    if pm is not None:
        return pm
    return PROMPT_MANAGER

def _runtime_chat_ai() -> str | None:
    """AI provider currently selected for normal Sona chat (`$c`/`$o`/`$g`, etc.)."""
    from .module import MANAGER

    for source in (_live_sonata(), MANAGER):
        if source is None:
            continue
        try:
            cfg = getattr(source, "config", None)
            if cfg is None:
                continue
            ai = cfg.get("AI") if hasattr(cfg, "get") else None
            if ai:
                return str(ai)
        except Exception:
            logger.debug("Could not read runtime chat AI from %r", source, exc_info=True)
    return None

async def _translate_thread_final_for_sona(
    text: str,
    *,
    user_prompt: str = "",
    user_name: str = "User",
) -> str:
    """Route thread-bound finals through live Sonata PromptManager (fail-open).

    Dedicated no-tools system instruction (self-commands persona + translate
    rules) and only the latest user prompt as chat history — not live
    get_instructions(), which includes the $command tool list.
    """
    from .module import PROMPT_MANAGER

    pm = _live_prompt_manager()
    send = getattr(pm, "send", None) or PROMPT_MANAGER.send
    original = text or ""
    prompt = _build_user_prompt(
        original.strip(),
        user=user_name,
        message=user_prompt,
    )
    return await atranslate_final(
        original,
        send=send,
        instructions=DEFAULT_SONA_INSTRUCTIONS,
        prompt=prompt,
        ai=_runtime_chat_ai(),
        model=None,
    )

async def _maybe_rename_thread(channel, title: str | None) -> None:
    if not title or not _channel_is_thread(channel):
        return
    name = _sanitize_thread_title(title)
    current = str(getattr(channel, "name", "") or "")
    if not name or name == current:
        return
    try:
        await channel.edit(name=name)
    except Exception:
        logger.debug("Could not rename Cursor thread to %r", name, exc_info=True)

async def _resolve_discord_channel(guild, client, channel_id: str | int):
    """Resolve a channel or thread id (guild cache often misses threads)."""
    try:
        cid = int(channel_id)
    except (TypeError, ValueError):
        return None
    ch = None
    if guild is not None:
        getter = getattr(guild, "get_channel", None)
        if callable(getter):
            ch = getter(cid)
        if ch is None:
            thread_getter = getattr(guild, "get_thread", None)
            if callable(thread_getter):
                ch = thread_getter(cid)
    if ch is None and client is not None:
        getter = getattr(client, "get_channel", None)
        if callable(getter):
            ch = getter(cid)
    if ch is None and client is not None and hasattr(client, "fetch_channel"):
        try:
            ch = await client.fetch_channel(cid)
        except Exception:
            ch = None
    return ch

def _interaction_shim_for_channel(
    channel,
    *,
    user_id: str | int,
    guild_id: str | int = 0,
    guild=None,
    client=None,
    response_done: bool = False,
    user=None,
):
    """Compat alias — returns ``ChannelUI.for_channel`` (never patches channel.send)."""
    return ChannelUI.for_channel(
        channel,
        user_id=user_id,
        guild_id=guild_id,
        guild=guild,
        client=client if client is not None else get_runtime().bot,
        user=user,
        response_done=response_done,
    )

def _interaction_shim_from_message(message: discord.Message):
    """Compat alias — returns ``ChannelUI.from_message``."""
    return ChannelUI.from_message(message, client=get_runtime().bot)

async def _create_public_agent_thread(
    *,
    parent_channel,
    starter_message: discord.Message | None,
    thread_name: str,
):
    """Create a public thread; prefer message-rooted threads when possible."""
    if starter_message is not None:
        return await starter_message.create_thread(
            name=thread_name,
            auto_archive_duration=60,
        )
    return await parent_channel.create_thread(
        name=thread_name,
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
        reason="Cursor agent thread session",
    )
