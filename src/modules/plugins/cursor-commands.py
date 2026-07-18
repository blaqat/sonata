"""
Cursor Commands
---------------
Discord slash-command adapter for Cursor Cloud Agents (`/cursor …`).

Core API/session/access logic lives in ``cursor_cloud``; this plugin only wires
Discord interactions, channel policies, and Beacon persistence.

Deliberate limitation: retained image bytes for pending approvals and idle/model
decisions are process-local (not Beacon). After a bot restart, text-only pending
approvals survive; multimodal pending work fails closed and the requester must
resubmit with attachments. Cleanup runs from ``SonataClient.close()`` — py-cord
does not dispatch ``on_close``.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import timedelta
from typing import Any

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands as ext_commands

from cursor_cloud.access import (
    AccessController,
    MemoryAccessStore,
    ImageRetentionStore,
    new_id,
    redact_preview,
)
from cursor_cloud.client import CursorCloudClient
from cursor_cloud.config import DEFAULT_PLUGIN_CONFIG, load_cursor_config
from cursor_cloud.context import (
    build_run_prompt,
    collect_chain_attachments,
    encode_image_bytes,
    images_from_discord_attachments,
    metas_from_images,
    metas_match,
    parse_message_reference,
)
from cursor_cloud.discord_cdn import DiscordCDNDownloader
from cursor_cloud.errors import (
    AuthorizationError,
    BusyRunError,
    ConfigurationError,
    CursorCloudError,
    GrantConsumedError,
    OwnershipError,
    StaleStateError,
    ValidationError,
)
from cursor_cloud.models import (
    AccessTier,
    AgentSession,
    IdleChoice,
    IdleDecision,
    ImageInput,
    ModelChoice,
    ModelDecision,
    PromptImageMeta,
    RunRequestEnvelope,
    RunStatus,
    ScopeKey,
    utcnow,
)
from cursor_cloud.run_log import (
    HISTORY_FOCUS_KINDS,
    MemoryRunLogStore,
    format_history_message,
    sanitize_log_summary,
)
from cursor_cloud.run_tracker import RunTracker
from cursor_cloud.session_store import (
    MemorySessionStore,
    run_is_busy,
    session_is_idle,
)
from cursor_cloud.status_renderer import initial_queued_message, redact_untrusted
from cursor_cloud.thread_session import (
    owner_reply_to_human,
    policy_channel_id as resolve_policy_channel_id,
    thread_session_immutable_violation,
)
from cursor_cloud.thread_renderer import THREAD_THINKING_INDICATOR
from cursor_cloud.thread_sink import ThreadActivitySink
from modules.AI_manager import AI_Manager
from modules.utils import get_reference_chain, get_reference_message_chain

logger = logging.getLogger("sonata.cursor")

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(
    lazy=True,
    config=dict(DEFAULT_PLUGIN_CONFIG),
)
__plugin_name__ = "cursor"
__dependencies__ = ["beacon", "chat"]

# Module-level runtime state populated on plugin load / bot ready.
_STATE: dict[str, Any] = {
    "config": None,
    "client": None,
    "cdn": None,
    "sessions": None,
    "run_logs": None,
    "access_store": None,
    "access": None,
    "bot": None,
    "trackers": {},
    "views_registered": False,
    "expiry_task": None,
    "reconcile_task": None,
    "policy_manager": None,  # injectable for tests / resolved from Sonata
    "handled_thread_messages": set(),
}


CONTENT_MENTIONS = discord.AllowedMentions(
    everyone=False, users=False, roles=False, replied_user=False
)


def _cfg():
    return _STATE["config"]


def _sessions() -> MemorySessionStore:
    return _STATE["sessions"]


def _run_logs() -> MemoryRunLogStore:
    store = _STATE.get("run_logs")
    if store is None:
        store = MemoryRunLogStore()
        _STATE["run_logs"] = store
    return store


def _access() -> AccessController:
    return _STATE["access"]


def _client() -> CursorCloudClient:
    return _STATE["client"]


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


def _resolve_policy_manager(interaction: discord.Interaction | None = None):
    """Return ChannelPolicies-like manager or None. Injectable via _STATE for tests."""
    injected = _STATE.get("policy_manager")
    if injected is not None:
        return injected
    sona = None
    bot = _STATE.get("bot")
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


def _require_policy_manager() -> bool:
    """Whether missing channel policy must fail closed."""
    if _STATE.get("require_policy") is False:
        return False
    if _STATE.get("require_policy") is True:
        return True
    bot = _STATE.get("bot")
    return bool(bot is not None and getattr(bot, "sonata", None) is not None)


def _policy_allowed_for(
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
    policy_manager = _resolve_policy_manager(interaction)
    if policy_manager is None:
        return not _require_policy_manager()
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


async def _policy_allowed(interaction: discord.Interaction, subcommand: str) -> bool:
    return _policy_allowed_for(
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
    cfg = _cfg()
    if cfg is None or not cfg.enabled:
        raise ConfigurationError("Cursor commands are disabled.")
    err = cfg.readiness_error()
    if err and str(user_id) != (cfg.god_user_id or ""):
        raise ConfigurationError(err)
    tier = await _access().resolve_tier(user_id)
    if tier == AccessTier.DENIED or int(tier) > int(minimum):
        raise AuthorizationError()
    if not await _access().can_use_command(user_id, subcommand):
        raise AuthorizationError()
    policy_manager = _resolve_policy_manager(interaction)
    if policy_manager is None and _require_policy_manager():
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
    cfg = _cfg()
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


class BeaconSessionStore(MemorySessionStore):
    def __init__(self, beacon_branch, *, max_recent: int = 20):
        super().__init__(max_recent=max_recent)
        self.beacon = beacon_branch
        self._load()

    def _load(self) -> None:
        try:
            data = self.beacon.discover("sessions")
            if isinstance(data, dict):
                self.import_state(data)
        except Exception:
            logger.exception("Failed loading Cursor sessions from Beacon")

    def _persist(self) -> None:
        try:
            self.beacon.illuminate("sessions", self.export_state())
        except Exception:
            logger.exception("Failed persisting Cursor sessions")

    async def upsert(self, session: AgentSession) -> AgentSession:
        result = await super().upsert(session)
        self._persist()
        return result

    async def set_active(self, scope: ScopeKey, agent_id: str) -> AgentSession:
        result = await super().set_active(scope, agent_id)
        self._persist()
        return result

    async def touch_activity(self, scope: ScopeKey, agent_id: str | None = None) -> None:
        await super().touch_activity(scope, agent_id)
        self._persist()

    async def save_idle_decision(self, decision: IdleDecision) -> IdleDecision:
        result = await super().save_idle_decision(decision)
        self._persist()
        return result

    async def reserve_idle_decision(self, decision: IdleDecision) -> IdleDecision | None:
        result = await super().reserve_idle_decision(decision)
        if result is not None:
            self._persist()
        return result

    async def save_model_decision(self, decision: ModelDecision) -> ModelDecision:
        result = await super().save_model_decision(decision)
        self._persist()
        return result

    async def reserve_model_decision(
        self, decision: ModelDecision
    ) -> ModelDecision | None:
        result = await super().reserve_model_decision(decision)
        if result is not None:
            self._persist()
        return result

    async def save_pending_payload(self, decision_id: str, payload: dict[str, Any]) -> None:
        await super().save_pending_payload(decision_id, payload)
        self._persist()

    async def pop_pending_payload(self, decision_id: str) -> dict[str, Any] | None:
        result = await super().pop_pending_payload(decision_id)
        self._persist()
        return result

    async def set_model_pref(self, scope: ScopeKey, model_id: str) -> None:
        await super().set_model_pref(scope, model_id)
        self._persist()


class BeaconRunLogStore(MemoryRunLogStore):
    def __init__(self, beacon_branch, **kwargs):
        super().__init__(**kwargs)
        self.beacon = beacon_branch
        self._load()

    def _load(self) -> None:
        try:
            data = self.beacon.discover("run_logs")
            if isinstance(data, dict):
                self.import_state(data)
        except Exception:
            logger.exception("Failed loading Cursor run logs from Beacon")

    def _persist(self) -> None:
        try:
            self.beacon.illuminate("run_logs", self.export_state())
        except Exception:
            logger.exception("Failed persisting Cursor run logs")

    async def append(self, scope, *, agent_id, run_id, kind, summary, detail=None):
        await super().append(
            scope,
            agent_id=agent_id,
            run_id=run_id,
            kind=kind,
            summary=summary,
            detail=detail,
        )
        self._persist()


class BeaconAccessStore(MemoryAccessStore):
    def __init__(self, beacon_branch, *, audit_limit: int = 200):
        super().__init__(audit_limit=audit_limit)
        self.beacon = beacon_branch
        self._load()

    def _load(self) -> None:
        try:
            data = self.beacon.discover("access")
            if isinstance(data, dict):
                self.import_state(data)
        except Exception:
            logger.exception("Failed loading Cursor access from Beacon")

    def _persist(self) -> None:
        try:
            self.beacon.illuminate("access", self.export_state())
        except Exception:
            logger.exception("Failed persisting Cursor access")

    async def set_overlay(self, overlay: dict[str, Any]) -> None:
        await super().set_overlay(overlay)
        self._persist()

    async def save_request(self, request):
        result = await super().save_request(request)
        self._persist()
        return result

    async def save_grant(self, grant):
        result = await super().save_grant(grant)
        self._persist()
        return result

    async def append_audit(self, event) -> None:
        await super().append_audit(event)
        self._persist()


# ---------------------------------------------------------------------------
# Persistent views
# ---------------------------------------------------------------------------


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


def _cdn() -> DiscordCDNDownloader:
    cdn = _STATE.get("cdn")
    if cdn is None:
        cfg = _cfg()
        cdn = DiscordCDNDownloader(
            max_bytes=cfg.max_image_bytes if cfg else 15 * 1024 * 1024
        )
        _STATE["cdn"] = cdn
    return cdn


async def _download_images(images: list[ImageInput]) -> list[ImageInput]:
    """Download Discord CDN URLs via unauthenticated allowlisted client.

    Never reuse the Cursor API Basic-auth client. Fail closed on host/redirect
    violations rather than falling back to raw CDN URLs for pending approvals.
    """
    cfg = _cfg()
    downloader = _cdn()
    out: list[ImageInput] = []
    total = 0
    for img in images:
        if img.data_b64:
            size = img.size_bytes or 0
            if total + size > cfg.max_retained_image_bytes:
                raise ValidationError(
                    "Retained image budget exceeded",
                    user_message="Images exceed the retention budget; reduce attachments and retry.",
                )
            out.append(img)
            total += size
            continue
        if not img.url:
            raise ValidationError(
                "Image missing url/data",
                user_message="An image could not be retained; resubmit the run.",
            )
        data, mime = await downloader.download(img.url, expected_mime=img.mime_type)
        if total + len(data) > cfg.max_retained_image_bytes:
            raise ValidationError(
                "Retained image budget exceeded",
                user_message="Images exceed the retention budget; reduce attachments and retry.",
            )
        encoded = encode_image_bytes(data, mime)
        encoded.source_message_id = img.source_message_id
        encoded.url = img.url
        out.append(encoded)
        total += len(data)
    return out


def _serializable_pending(
    *,
    prompt: str,
    prompt_text: str,
    message_ref: str | None,
    preferred: str | None,
    image_metas: list,
    retention_key: str | None,
    skipped: list[str] | None = None,
    scope: ScopeKey | None = None,
) -> dict[str, Any]:
    """Durable decision payload (no API secrets / no raw unbounded image bytes)."""
    data: dict[str, Any] = {
        "prompt": prompt,
        "prompt_text": prompt_text,
        "message_ref": message_ref,
        "preferred": preferred,
        "image_metas": [
            m.to_dict() if hasattr(m, "to_dict") else dict(m) for m in image_metas
        ],
        "retention_key": retention_key,
        "skipped": list(skipped or []),
    }
    if scope is not None:
        data["guild_id"] = scope.guild_id
        data["channel_id"] = scope.channel_id
        data["user_id"] = scope.user_id
    return data


async def _rehydrate_pending_images(pending: dict[str, Any]) -> list[ImageInput]:
    """Load retained images for a decision; fail closed on missing/mismatch.

    Image bytes are process-local: after restart, multimodal pending decisions
    cannot be rehydrated and the user must resubmit with attachments.
    """
    key = pending.get("retention_key")
    expected_raw = list(pending.get("image_metas") or [])
    expected = [
        PromptImageMeta.from_dict(m) if isinstance(m, dict) else m for m in expected_raw
    ]
    restart_msg = (
        "Pending run images are only kept in memory and do not survive bot "
        "restarts; please resubmit the run with attachments."
    )
    if not key:
        if expected:
            raise ValidationError(
                "Pending images missing retention key",
                user_message=restart_msg,
            )
        return []
    images = await _access().images.get(str(key)) or []
    if expected and (not images or not metas_match(expected, metas_from_images(images))):
        raise ValidationError(
            "Pending image metadata mismatch or process-local retention lost",
            user_message=restart_msg,
        )
    if not expected and not images:
        return []
    return images


async def _discard_retention_key(key: str | None) -> None:
    if key:
        await _access().images.discard(str(key))


async def _delete_or_edit_status_msg(
    status_msg: discord.Message | None, content: str
) -> None:
    """Remove orphan public status when launch aborts (busy/race)."""
    if status_msg is None:
        return
    try:
        await status_msg.delete()
        return
    except Exception:
        pass
    try:
        await status_msg.edit(content=content[:2000], view=None, allowed_mentions=CONTENT_MENTIONS)
    except Exception:
        logger.debug("Could not clean up orphan Cursor status message", exc_info=True)


async def _build_context_for_run(
    interaction: discord.Interaction,
    prompt: str,
    message_ref: str | None,
    image_attachments: list[discord.Attachment | None],
) -> tuple[str, list[ImageInput], list[str]]:
    cfg = _cfg()
    missing: list[str] = []
    chain_messages = []
    ref_chain = None

    channel_id, message_id = parse_message_reference(
        message_ref,
        current_guild_id=interaction.guild_id,
        current_channel_id=interaction.channel_id,
    )
    target_message = None
    if message_id:
        channel = interaction.channel
        if channel_id and str(channel_id) != str(interaction.channel_id):
            channel = interaction.guild.get_channel(int(channel_id)) if interaction.guild else None
            if channel is None and interaction.guild:
                try:
                    channel = await interaction.guild.fetch_channel(int(channel_id))
                except Exception:
                    channel = None
        if channel is None:
            missing.append(f"Could not access channel for message {message_id}.")
        else:
            try:
                target_message = await channel.fetch_message(int(message_id))
            except Exception:
                missing.append(f"Message {message_id} missing or inaccessible.")

    if target_message is not None:
        try:
            ref_chain = await get_reference_chain(
                target_message, max_length=cfg.chain_depth, include_message=True
            )
        except Exception:
            ref_chain = None
            missing.append("Failed to resolve full reply chain text.")
        try:
            msg_objs = await get_reference_message_chain(
                target_message, max_length=cfg.chain_depth, include_message=True
            )
            chain_messages = collect_chain_attachments(msg_objs, max_depth=cfg.chain_depth)
        except Exception:
            missing.append("Failed to resolve reply-chain attachments.")

    direct: list[ImageInput] = []
    for att in image_attachments:
        if att is None:
            continue
        direct.extend(
            images_from_discord_attachments(
                [att], source_message_id=str(interaction.id)
            )
        )

    built = build_run_prompt(
        prompt,
        reference_chain=ref_chain,
        chain_messages=chain_messages,
        direct_images=direct,
        missing_refs=missing,
        max_images=cfg.max_images,
        max_bytes=cfg.max_image_bytes,
    )
    return built.text, built.images, built.skipped_images


async def _build_context_from_message(
    message: discord.Message,
    prompt: str,
    *,
    message_ref: str | None = None,
    image_attachments: list[discord.Attachment | None] | None = None,
) -> tuple[str, list[ImageInput], list[str]]:
    cfg = _cfg()
    missing: list[str] = []
    chain_messages = []
    ref_chain = None

    channel_id, ref_message_id = parse_message_reference(
        message_ref,
        current_guild_id=message.guild.id if message.guild else None,
        current_channel_id=message.channel.id,
    )
    target_message = message
    if ref_message_id and str(ref_message_id) != str(message.id):
        channel = message.channel
        if channel_id and str(channel_id) != str(message.channel.id):
            channel = message.guild.get_channel(int(channel_id)) if message.guild else None
            if channel is None and message.guild:
                try:
                    channel = await message.guild.fetch_channel(int(channel_id))
                except Exception:
                    channel = None
        if channel is None:
            missing.append(f"Could not access channel for message {ref_message_id}.")
        else:
            try:
                target_message = await channel.fetch_message(int(ref_message_id))
            except Exception:
                missing.append(f"Message {ref_message_id} missing or inaccessible.")

    if target_message is not None:
        try:
            ref_chain = await get_reference_chain(
                target_message, max_length=cfg.chain_depth, include_message=True
            )
        except Exception:
            ref_chain = None
            missing.append("Failed to resolve full reply chain text.")
        try:
            msg_objs = await get_reference_message_chain(
                target_message, max_length=cfg.chain_depth, include_message=True
            )
            chain_messages = collect_chain_attachments(msg_objs, max_depth=cfg.chain_depth)
        except Exception:
            missing.append("Failed to resolve reply-chain attachments.")

    direct: list[ImageInput] = []
    for att in list(message.attachments) + list(image_attachments or []):
        if att is None:
            continue
        direct.extend(
            images_from_discord_attachments(
                [att], source_message_id=str(message.id)
            )
        )

    built = build_run_prompt(
        prompt,
        reference_chain=ref_chain,
        chain_messages=chain_messages,
        direct_images=direct,
        missing_refs=missing,
        max_images=cfg.max_images,
        max_bytes=cfg.max_image_bytes,
    )
    return built.text, built.images, built.skipped_images


async def _maybe_unarchive_thread(thread: discord.Thread) -> None:
    if not getattr(thread, "archived", False):
        return
    try:
        await thread.edit(archived=False)
    except Exception:
        logger.debug("Could not unarchive Cursor thread %s", thread.id, exc_info=True)


async def handle_thread_message(message: discord.Message) -> bool:
    """Owner plain messages in bound threads become agent follow-ups."""
    if message.author.bot:
        return False
    if not _channel_is_thread(message.channel):
        return False
    if not message.content and not message.attachments:
        return False

    sessions = _sessions()
    session = await sessions.find_thread_session(str(message.channel.id))
    if session is None:
        return False

    seen: set[str] = _STATE.setdefault("handled_thread_messages", set())
    msg_key = str(message.id)
    if msg_key in seen:
        return True
    if len(seen) > 5000:
        seen.clear()
    seen.add(msg_key)

    owner_id = session.owner_id
    if str(message.author.id) != owner_id:
        return True

    resolved_reply = None
    ref = getattr(message, "reference", None)
    if ref is not None and getattr(ref, "message_id", None) is not None:
        resolved_reply = getattr(ref, "resolved", None)
        if resolved_reply is None:
            try:
                resolved_reply = await message.channel.fetch_message(int(ref.message_id))
            except Exception:
                resolved_reply = None
    if owner_reply_to_human(message, owner_id, resolved_message=resolved_reply):
        return True

    await _maybe_unarchive_thread(message.channel)

    prompt = (message.content or "").strip()
    if not prompt and not message.attachments:
        return False

    # Immediate thinking indicator so follow-ups don't look stuck while we
    # auth / build context / hit the Cursor API (slash Queued equivalent).
    activity_msg = None
    if session.status_channel_id and session.status_message_id:
        try:
            activity_msg = await message.channel.fetch_message(
                int(session.status_message_id)
            )
        except Exception:
            activity_msg = None
    if activity_msg is None:
        try:
            activity_msg = await message.channel.send(
                THREAD_THINKING_INDICATOR,
                allowed_mentions=CONTENT_MENTIONS,
            )
            session.status_channel_id = str(message.channel.id)
            session.status_message_id = str(activity_msg.id)
            await sessions.upsert(session)
        except Exception:
            logger.exception("Cursor thread activity message create failed")
            return True
    else:
        try:
            await activity_msg.edit(
                content=THREAD_THINKING_INDICATOR,
                allowed_mentions=CONTENT_MENTIONS,
            )
        except Exception:
            logger.debug("Cursor thread thinking indicator edit failed", exc_info=True)

    scope = _scope_from_message(message, user_id=owner_id)
    pol_ch = resolve_policy_channel_id(
        channel_id=scope.channel_id,
        session=session,
    )
    role_ids = _role_ids(message.author)
    try:
        await _revalidate_run_auth(
            user_id=owner_id,
            guild_id=scope.guild_id,
            channel_id=scope.channel_id,
            role_ids=role_ids,
            subcommand="run",
            interaction=None,
            policy_channel_id=pol_ch,
        )
    except CursorCloudError:
        # Already marked seen — do not let other handlers re-process as unbound.
        return True

    fake = _interaction_shim_from_message(message)

    try:
        prompt_text, image_inputs, skipped = await _build_context_from_message(
            message, prompt or "(see attachments)"
        )
    except Exception:
        logger.exception("Cursor thread follow-up context failed")
        return True

    try:
        await _prepare_and_maybe_launch(
            fake,  # type: ignore
            prompt or "(see attachments)",
            None,
            [],
            force_new=False,
            scope_override=scope,
            policy_channel_id=pol_ch,
            thread_bound=True,
            parent_channel_id=session.parent_channel_id,
            status_msg=activity_msg,
            skip_status_post=True,
            prebuilt=(prompt_text, image_inputs, skipped),
        )
    except BusyRunError:
        try:
            await message.channel.send(
                f"### Busy\n{BusyRunError().user_message}"[:2000],
                allowed_mentions=CONTENT_MENTIONS,
            )
        except Exception:
            pass
    except CursorCloudError as exc:
        try:
            await message.channel.send(
                f"### Error\n{exc.user_message}"[:2000],
                allowed_mentions=CONTENT_MENTIONS,
            )
        except Exception:
            pass
    except Exception:
        logger.exception("Cursor thread follow-up failed")
    return True


async def _launch_run(
    interaction: discord.Interaction,
    *,
    prompt_text: str,
    images: list[ImageInput],
    skipped: list[str],
    agent_id: str | None,
    force_new: bool,
    model: str | None,
    grant=None,
    envelope: RunRequestEnvelope | None = None,
    scope: ScopeKey | None = None,
    role_ids: list[str] | None = None,
    skip_status_post: bool = False,
    status_msg: discord.Message | None = None,
    thread_bound: bool = False,
    parent_channel_id: str | None = None,
    policy_channel_id: str | None = None,
    agent_display_name: str | None = None,
) -> AgentSession:
    cfg = _cfg()
    scope = scope or _scope_from_interaction(interaction)
    sessions = _sessions()
    client = _client()
    role_ids = role_ids if role_ids is not None else _role_ids(getattr(interaction, "user", None) or type("U", (), {"roles": []})())
    interaction_obj = interaction if isinstance(interaction, discord.Interaction) else None
    # Inherit binding from an existing active session when callers omit flags
    # (e.g. classic /cursor run inside a bound thread).
    active_for_bind = await sessions.get_active(scope)
    if active_for_bind is not None and active_for_bind.thread_bound:
        thread_bound = True
        parent_channel_id = parent_channel_id or active_for_bind.parent_channel_id
    pol_ch = resolve_policy_channel_id(
        channel_id=scope.channel_id,
        session=active_for_bind,
        parent_channel_id=policy_channel_id or parent_channel_id,
    )
    auth_subcommand = "new" if thread_bound and force_new else "run"

    # Final fail-closed auth immediately before consume/submit.
    await _revalidate_run_auth(
        user_id=scope.user_id,
        guild_id=scope.guild_id,
        channel_id=scope.channel_id,
        role_ids=role_ids,
        subcommand=auth_subcommand,
        interaction=interaction_obj,
        policy_channel_id=pol_ch,
    )

    # Pre-check busy under the scope lock BEFORE posting public Queued status,
    # so concurrent callers cannot leave orphan status messages.
    async with sessions.lock_for(scope):
        await _revalidate_run_auth(
            user_id=scope.user_id,
            guild_id=scope.guild_id,
            channel_id=scope.channel_id,
            role_ids=role_ids,
            subcommand=auth_subcommand,
            interaction=interaction_obj,
            policy_channel_id=pol_ch,
        )
        active = await sessions.get_active(scope)
        if thread_bound and active is not None and thread_session_immutable_violation(
            active, force_new=force_new, agent_id=agent_id
        ):
            raise ValidationError(
                "Thread session immutable",
                user_message="This thread is already bound to a Cursor session.",
            )
        resolved_agent = agent_id
        if not force_new and resolved_agent is None and active is not None:
            resolved_agent = active.agent_id
        if resolved_agent and not force_new:
            session = await sessions.get_session(scope, resolved_agent)
            if session and run_is_busy(session.latest_run_status):
                raise BusyRunError()

    # Post status only after the busy pre-check passed (Discord I/O outside lock).
    if status_msg is None and not skip_status_post:
        status_msg = await _public(interaction, initial_queued_message())

    status_cleanup: tuple[str, str] | None = None  # (kind, message)
    grant_consumed = False
    session: AgentSession | None = None
    pending_exc: BaseException | None = None

    try:
        async with sessions.lock_for(scope):
            # Re-check auth + busy BEFORE consuming a one-run grant.
            await _revalidate_run_auth(
                user_id=scope.user_id,
                guild_id=scope.guild_id,
                channel_id=scope.channel_id,
                role_ids=role_ids,
                subcommand=auth_subcommand,
                interaction=interaction_obj,
                policy_channel_id=pol_ch,
            )
            active = await sessions.get_active(scope)
            if thread_bound and active is not None and thread_session_immutable_violation(
                active, force_new=force_new, agent_id=agent_id
            ):
                raise ValidationError(
                    "Thread session immutable",
                    user_message="This thread is already bound to a Cursor session.",
                )
            if not force_new and agent_id is None and active is not None:
                agent_id = active.agent_id

            if agent_id and not force_new:
                existing = await sessions.get_session(scope, agent_id)
                if existing and run_is_busy(existing.latest_run_status):
                    status_cleanup = (
                        "busy",
                        "### Busy\n" + BusyRunError().user_message,
                    )
                    raise BusyRunError()

            # Consume one-run grants only after busy rejection, under the same
            # lock as API submit (prevents concurrent duplicate creates).
            if grant is not None and getattr(grant, "kind", None) == "once" and not getattr(
                grant, "consumed", False
            ):
                if envelope is None:
                    raise ValidationError(
                        "Missing envelope for one-run grant consume",
                        user_message=(
                            "Approval grant could not be consumed safely; please resubmit."
                        ),
                    )
                grant = await _access().consume_grant_for_submit(grant, envelope)
                grant_consumed = True

            # Defensive: if busy somehow appears after consume, fail-closed.
            if agent_id and not force_new:
                existing = await sessions.get_session(scope, agent_id)
                if existing and run_is_busy(existing.latest_run_status):
                    if grant_consumed and grant is not None:
                        await _access().mark_submit_failed_after_consume(grant)
                    status_cleanup = (
                        "busy",
                        "### Busy\n" + BusyRunError().user_message,
                    )
                    raise BusyRunError()

            api_images = [img.to_api() for img in images]
            try:
                if force_new or not agent_id:
                    suggested_name = (
                        _sanitize_thread_title(agent_display_name)
                        if agent_display_name
                        else None
                    )
                    agent, run = await client.create_agent(
                        prompt_text,
                        images=api_images or None,
                        model=model or cfg.default_model or None,
                        repository_url=cfg.default_repository_url,
                        starting_ref=cfg.default_ref,
                        auto_create_pr=cfg.auto_create_pr,
                        name=suggested_name,
                    )
                    session_name = (agent.name or suggested_name or "").strip()
                    session = AgentSession(
                        scope=scope,
                        agent_id=agent.id,
                        owner_id=scope.user_id,
                        name=session_name,
                        model=model or cfg.default_model or agent.model,
                        preferred_model=model or cfg.default_model or None,
                        repository_url=cfg.default_repository_url,
                        starting_ref=cfg.default_ref,
                        latest_run_id=run.id,
                        latest_run_status=run.status,
                        status_channel_id=(
                            str(status_msg.channel.id) if status_msg else None
                        ),
                        status_message_id=str(status_msg.id) if status_msg else None,
                        thread_bound=thread_bound,
                        parent_channel_id=parent_channel_id,
                        summary=prompt_text[:200],
                        active=True,
                        last_meaningful_activity_at=utcnow(),
                    )
                    await sessions.upsert(session)
                    if thread_bound and status_msg is not None:
                        # Prefer API-provided agent name when present.
                        await _maybe_rename_thread(
                            status_msg.channel, agent.name or suggested_name
                        )
                else:
                    run = await client.create_run(
                        agent_id, prompt_text, images=api_images or None
                    )
                    session = await sessions.get_session(scope, agent_id)
                    if session is None:
                        raise OwnershipError()
                    session.latest_run_id = run.id
                    session.latest_run_status = run.status
                    if status_msg is not None:
                        session.status_channel_id = str(status_msg.channel.id)
                        session.status_message_id = str(status_msg.id)
                    session.summary = prompt_text[:200]
                    session.last_meaningful_activity_at = utcnow()
                    await sessions.upsert(session)
            except BusyRunError:
                if grant_consumed and grant is not None:
                    await _access().mark_submit_failed_after_consume(grant)
                status_cleanup = (
                    "busy",
                    "### Busy\n" + BusyRunError().user_message,
                )
                raise
            except Exception as exc:
                if (
                    grant_consumed
                    and grant is not None
                    and getattr(grant, "kind", None) == "once"
                ):
                    await _access().mark_submit_failed_after_consume(grant)
                    status_cleanup = (
                        "grant",
                        "### Error\n" + GrantConsumedError(str(exc)).user_message,
                    )
                    raise GrantConsumedError(str(exc)) from exc
                status_cleanup = (
                    "error",
                    "### Error\n"
                    + redact_untrusted(getattr(exc, "user_message", str(exc))),
                )
                raise
    except Exception as exc:
        pending_exc = exc

    # Discord status cleanup/edit OUTSIDE the scope lock (slow I/O).
    if status_cleanup is not None:
        kind, content = status_cleanup
        if kind == "busy":
            await _delete_or_edit_status_msg(status_msg, content)
        elif status_msg is not None:
            try:
                await status_msg.edit(
                    content=content[:2000],
                    allowed_mentions=CONTENT_MENTIONS,
                )
            except Exception:
                logger.debug("Failed to edit Cursor status after error", exc_info=True)

    if pending_exc is not None:
        raise pending_exc
    if session is None:
        raise BusyRunError()

    if status_msg is not None:
        async def on_activity(_event: str):
            await sessions.touch_activity(scope, session.agent_id)

        run_logs = _run_logs()
        try:
            await run_logs.append(
                scope,
                agent_id=session.agent_id,
                run_id=session.latest_run_id or "",
                kind="prompt",
                summary=sanitize_log_summary(prompt_text),
            )
        except Exception:
            logger.debug("Failed to append Cursor prompt log", exc_info=True)

        sink: DiscordStatusSink | ThreadActivitySink
        if thread_bound or session.thread_bound:
            channel = status_msg.channel if status_msg else interaction.channel
            sink = ThreadActivitySink(
                channel,
                status_msg,
                edit_interval_ms=cfg.status_edit_interval_ms,
                allowed_mentions=CONTENT_MENTIONS,
            )
        else:
            sink = DiscordStatusSink(status_msg)
        tracker = RunTracker(
            client,
            sink,
            edit_interval_ms=cfg.status_edit_interval_ms,
            agent_name=session.name or session.agent_id,
            skipped_images=skipped,
            on_meaningful_activity=on_activity,
            run_log=run_logs,
            scope=scope,
        )

        async def _runner():
            try:
                snap = await tracker.track(
                    session.agent_id,
                    session.latest_run_id,
                    initial_status=session.latest_run_status,
                )
                session.latest_run_status = snap.status
                session.degraded = snap.degraded or getattr(sink, "degraded", False)
                if snap.status.is_terminal:
                    session.last_meaningful_activity_at = utcnow()
                    branches = list(getattr(snap, "git_branches", None) or [])
                    if branches:
                        session.latest_git = [
                            g.to_dict() if hasattr(g, "to_dict") else dict(g)
                            for g in branches
                        ]
                await sessions.upsert(session)
            finally:
                _STATE["trackers"].pop(session.agent_id, None)

        _STATE["trackers"][session.agent_id] = asyncio.create_task(_runner())
    return session


async def _rollback_decision(
    *,
    kind: str,
    decision_id: str,
    scope: ScopeKey,
    retention_key: str | None,
) -> None:
    sessions = _sessions()
    async with sessions.lock_for(scope):
        if kind == "model":
            decision = await sessions.get_model_decision(decision_id)
            if decision is not None:
                decision.consumed = True
                decision.choice = ModelChoice.CANCEL
                await sessions.save_model_decision(decision)
        else:
            decision = await sessions.get_idle_decision(decision_id)
            if decision is not None:
                decision.consumed = True
                decision.choice = IdleChoice.CANCEL
                await sessions.save_idle_decision(decision)
        await sessions.pop_pending_payload(decision_id)
    await _discard_retention_key(retention_key)


async def _offer_model_decision(
    interaction: discord.Interaction,
    *,
    scope: ScopeKey,
    active: AgentSession,
    preferred: str | None,
    prompt: str,
    prompt_text: str,
    message_ref: str | None,
    image_inputs: list[ImageInput],
    skipped: list[str],
) -> bool:
    """Reserve+post a model decision. Returns True if a prompt was posted/deduped."""
    sessions = _sessions()
    retained = await _download_images(image_inputs) if image_inputs else []
    retention_key = new_id("ret") if retained else None
    decision = ModelDecision(
        decision_id=new_id("mdl"),
        scope=scope,
        agent_id=active.agent_id,
        preferred_model=preferred or "",
        agent_model=active.model or "",
        expires_at=utcnow() + timedelta(minutes=30),
    )
    payload = _serializable_pending(
        prompt=prompt,
        prompt_text=prompt_text,
        message_ref=message_ref,
        preferred=preferred,
        image_metas=metas_from_images(retained or image_inputs),
        retention_key=retention_key,
        skipped=skipped,
        scope=scope,
    )

    async with sessions.lock_for(scope):
        active_now = await sessions.get_active(scope)
        still = (
            active_now is not None
            and preferred
            and active_now.model
            and preferred != active_now.model
        )
        if not still:
            return False
        existing = await sessions.find_open_model_decision(scope)
        if existing is not None:
            await _ephemeral(
                interaction,
                f"A model choice is already pending (`{existing.decision_id}`).",
            )
            return True
        if retention_key and retained:
            await _access().images.put(
                retention_key, retained, expires_at=decision.expires_at
            )
        await sessions.save_pending_payload(decision.decision_id, payload)
        reserved = await sessions.reserve_model_decision(decision)
        if reserved is None:
            await _discard_retention_key(retention_key)
            await sessions.pop_pending_payload(decision.decision_id)
            existing = await sessions.find_open_model_decision(scope)
            await _ephemeral(
                interaction,
                f"A model choice is already pending (`{getattr(existing, 'decision_id', '?')}`).",
            )
            return True

    view = ModelDecisionView(decision.decision_id)
    try:
        msg = await interaction.channel.send(
            f"### Model choice\n"
            f"<@{scope.user_id}> selected `{preferred}` but session "
            f"`{active.agent_id}` was created with `{active.model}`.\n"
            f"Follow-up runs cannot change model.",
            view=view,
            allowed_mentions=discord.AllowedMentions(
                users=True, everyone=False, roles=False
            ),
        )
    except Exception:
        await _rollback_decision(
            kind="model",
            decision_id=decision.decision_id,
            scope=scope,
            retention_key=retention_key,
        )
        raise

    decision.message_channel_id = str(msg.channel.id)
    decision.message_id = str(msg.id)
    await sessions.save_model_decision(decision)
    bot = _STATE.get("bot")
    if bot:
        bot.add_view(ModelDecisionView(decision.decision_id))
    await _ephemeral(
        interaction,
        "Model mismatch — choose how to proceed in the channel message.",
    )
    return True


async def _offer_idle_decision(
    interaction: discord.Interaction,
    *,
    scope: ScopeKey,
    active: AgentSession,
    preferred: str | None,
    prompt: str,
    prompt_text: str,
    message_ref: str | None,
    image_inputs: list[ImageInput],
    skipped: list[str],
) -> bool:
    """Reserve+post an idle decision. Returns True if a prompt was posted/deduped."""
    sessions = _sessions()
    cfg = _cfg()
    retained = await _download_images(image_inputs) if image_inputs else []
    retention_key = new_id("ret") if retained else None
    decision = IdleDecision(
        decision_id=new_id("idle"),
        scope=scope,
        agent_id=active.agent_id,
        expires_at=utcnow() + timedelta(minutes=30),
    )
    payload = _serializable_pending(
        prompt=prompt,
        prompt_text=prompt_text,
        message_ref=message_ref,
        preferred=preferred,
        image_metas=metas_from_images(retained or image_inputs),
        retention_key=retention_key,
        skipped=skipped,
        scope=scope,
    )

    async with sessions.lock_for(scope):
        active_now = await sessions.get_active(scope)
        still = active_now is not None and session_is_idle(
            active_now, idle_minutes=cfg.session_idle_prompt_minutes
        )
        if not still:
            return False
        existing = await sessions.find_open_idle_decision(scope)
        if existing is not None:
            await _ephemeral(
                interaction,
                f"An idle session choice is already pending (`{existing.decision_id}`).",
            )
            return True
        if retention_key and retained:
            await _access().images.put(
                retention_key, retained, expires_at=decision.expires_at
            )
        await sessions.save_pending_payload(decision.decision_id, payload)
        reserved = await sessions.reserve_idle_decision(decision)
        if reserved is None:
            await _discard_retention_key(retention_key)
            await sessions.pop_pending_payload(decision.decision_id)
            existing = await sessions.find_open_idle_decision(scope)
            await _ephemeral(
                interaction,
                f"An idle session choice is already pending (`{getattr(existing, 'decision_id', '?')}`).",
            )
            return True

    view = IdleDecisionView(decision.decision_id)
    try:
        msg = await interaction.channel.send(
            f"### Idle session\n"
            f"<@{scope.user_id}> — session `{active.agent_id}` has been idle. "
            f"Continue previous, start new, or cancel?",
            view=view,
            allowed_mentions=discord.AllowedMentions(
                users=True, everyone=False, roles=False
            ),
        )
    except Exception:
        await _rollback_decision(
            kind="idle",
            decision_id=decision.decision_id,
            scope=scope,
            retention_key=retention_key,
        )
        raise

    decision.message_channel_id = str(msg.channel.id)
    decision.message_id = str(msg.id)
    await sessions.save_idle_decision(decision)
    bot = _STATE.get("bot")
    if bot:
        bot.add_view(IdleDecisionView(decision.decision_id))
    await _ephemeral(
        interaction,
        "Session idle — choose how to proceed in the channel message.",
    )
    return True


async def _prepare_and_maybe_launch(
    interaction: discord.Interaction,
    prompt: str,
    message_ref: str | None,
    images: list[discord.Attachment | None],
    *,
    force_new: bool | None = None,
    skip_idle: bool = False,
    skip_model: bool = False,
    model_override_choice: ModelChoice | None = None,
    prebuilt: tuple[str, list[ImageInput], list[str]] | None = None,
    scope_override: ScopeKey | None = None,
    policy_channel_id: str | None = None,
    thread_bound: bool = False,
    parent_channel_id: str | None = None,
    status_msg: discord.Message | None = None,
    skip_status_post: bool = False,
    auth_subcommand: str | None = None,
    agent_display_name: str | None = None,
) -> str:
    """Prepare auth/context and launch (or post approval/decision).

    Returns one of: ``launched``, ``approval_pending``, ``decision_pending``.
    """
    scope = scope_override or _scope_from_interaction(interaction)
    sessions = _sessions()
    cfg = _cfg()
    role_ids = _role_ids(interaction.user)

    # Inherit immutable thread binding + parent policy when already bound,
    # or when the interaction channel is a Discord thread.
    active_early = await sessions.get_active(scope)
    if active_early is not None and active_early.thread_bound:
        thread_bound = True
        parent_channel_id = parent_channel_id or active_early.parent_channel_id
        if status_msg is None and active_early.status_message_id:
            try:
                ch = getattr(interaction, "channel", None)
                if ch is not None:
                    status_msg = await ch.fetch_message(int(active_early.status_message_id))
                    skip_status_post = True
            except Exception:
                status_msg = None
    if policy_channel_id is None and parent_channel_id is None:
        channel = getattr(interaction, "channel", None)
        if _channel_is_thread(channel) and getattr(channel, "parent_id", None):
            parent_channel_id = str(channel.parent_id)

    pol_ch = resolve_policy_channel_id(
        channel_id=scope.channel_id,
        session=active_early,
        parent_channel_id=policy_channel_id or parent_channel_id,
    )
    subcommand = auth_subcommand or ("new" if thread_bound and force_new else "run")

    # Gate DENIED / Tier3 and policy before any work.
    tier = await _revalidate_run_auth(
        user_id=scope.user_id,
        guild_id=scope.guild_id,
        channel_id=scope.channel_id,
        role_ids=role_ids,
        subcommand=subcommand,
        interaction=interaction,
        policy_channel_id=pol_ch,
    )

    if prebuilt is None:
        prompt_text, image_inputs, skipped = await _build_context_for_run(
            interaction, prompt, message_ref, images
        )
    else:
        prompt_text, image_inputs, skipped = prebuilt

    # Idle/model decisions MUST run before refreshing meaningful activity.
    active = await sessions.get_active(scope)
    preferred = None
    if active is not None:
        preferred = active.preferred_model or await sessions.get_model_pref(scope) or cfg.default_model or None
    else:
        preferred = await sessions.get_model_pref(scope) or cfg.default_model or None

    want_new = bool(force_new)
    if thread_bound or (active is not None and active.thread_bound):
        thread_bound = True
        parent_channel_id = parent_channel_id or (
            active.parent_channel_id if active else None
        )
        if active is not None and thread_session_immutable_violation(
            active, force_new=want_new, agent_id=None
        ):
            raise ValidationError(
                "Thread session immutable",
                user_message="This thread is already bound to a Cursor session.",
            )
        if active is not None and not want_new:
            want_new = False

    # Model mismatch before idle + approval hashing.
    if (
        not skip_model
        and active is not None
        and not want_new
        and preferred
        and active.model
        and preferred != active.model
        and model_override_choice is None
    ):
        posted = await _offer_model_decision(
            interaction,
            scope=scope,
            active=active,
            preferred=preferred,
            prompt=prompt,
            prompt_text=prompt_text,
            message_ref=message_ref,
            image_inputs=image_inputs,
            skipped=skipped,
        )
        if posted:
            return "decision_pending"
        # Condition cleared under lock (race); refresh and continue.
        active = await sessions.get_active(scope)

    if model_override_choice == ModelChoice.NEW_SESSION:
        want_new = True
    elif model_override_choice == ModelChoice.CONTINUE_ORIGINAL:
        want_new = False
        preferred = active.model if active else preferred

    if (
        not skip_idle
        and not want_new
        and active is not None
        and session_is_idle(active, idle_minutes=cfg.session_idle_prompt_minutes)
    ):
        posted = await _offer_idle_decision(
            interaction,
            scope=scope,
            active=active,
            preferred=preferred,
            prompt=prompt,
            prompt_text=prompt_text,
            message_ref=message_ref,
            image_inputs=image_inputs,
            skipped=skipped,
        )
        if posted:
            return "decision_pending"
        active = await sessions.get_active(scope)

    # Activity refresh only after idle/model gates have passed.
    await sessions.touch_activity(scope)

    agent_id = None if want_new else (active.agent_id if active else None)

    # Retain images once; envelope metas must match retained set exactly.
    retained_for_run = await _download_images(image_inputs) if image_inputs else []
    exact_metas = metas_from_images(retained_for_run)
    if image_inputs and not metas_match(exact_metas, metas_from_images(image_inputs)) and not all(
        i.data_b64 for i in image_inputs
    ):
        # After download, fingerprints change from URL→bytes; that is expected.
        # Require retained set to be the submission set going forward.
        pass
    submit_images = retained_for_run if retained_for_run else image_inputs

    envelope = RunRequestEnvelope(
        requester_id=scope.user_id,
        scope=scope,
        prompt_text=prompt_text,
        model=preferred if want_new or active is None else (active.model if active else preferred),
        repository_url=cfg.default_repository_url,
        starting_ref=cfg.default_ref,
        agent_id=agent_id,
        is_follow_up=bool(agent_id),
        image_metas=metas_from_images(submit_images),
    )

    grant = None
    if tier == AccessTier.APPROVAL:
        grant = await _access().find_valid_grant(scope, scope.user_id, envelope)
        if grant is None:
            retained = submit_images
            # Envelope already uses retained metas; store same set.
            if not metas_match(envelope.image_metas, metas_from_images(retained)):
                raise ValidationError(
                    "Image metadata mismatch",
                    user_message="Image set changed during preparation; please resubmit.",
                )
            status_channel_id = None
            status_message_id = None
            if status_msg is not None:
                status_channel_id = str(status_msg.channel.id)
                status_message_id = str(status_msg.id)
            elif active is not None:
                status_channel_id = active.status_channel_id
                status_message_id = active.status_message_id
            request = await _access().create_approval_request(
                envelope,
                prompt_preview=redact_preview(prompt),
                images=retained,
                thread_bound=thread_bound,
                parent_channel_id=(
                    (parent_channel_id or pol_ch) if thread_bound else parent_channel_id
                ),
                status_channel_id=status_channel_id,
                status_message_id=status_message_id,
            )
            approvers = await _access().current_approver_ids()
            mentions = " ".join(f"<@{uid}>" for uid in approvers)
            summary = (
                f"### Cursor approval\n"
                f"Requester: <@{scope.user_id}>\n"
                f"Scope: guild `{scope.guild_id}` channel `{scope.channel_id}`\n"
                f"Mode: {'follow-up' if envelope.is_follow_up else 'new agent'}\n"
                f"Repo: `{envelope.repository_url}` @ `{envelope.starting_ref}`\n"
                f"Model: `{envelope.model or 'default'}`\n"
                f"Images: {len(retained)}\n"
                f"Preview: {redact_preview(prompt)}\n"
                f"Request: `{request.request_id}`\n"
                f"{mentions}"
            )
            view = ApprovalView(request.request_id)
            approve_mentions = discord.AllowedMentions(
                everyone=False, users=True, roles=False, replied_user=False
            )
            await _ephemeral(
                interaction,
                f"Approval pending (`{request.request_id}`). Approvers have been notified.",
            )
            # Post approval in the parent channel for thread-bound new sessions
            # so approvers see it outside the private-feeling agent thread.
            approve_channel = interaction.channel
            if thread_bound and parent_channel_id:
                bot = _STATE.get("bot")
                try:
                    parent = None
                    if bot is not None:
                        parent = bot.get_channel(int(parent_channel_id))
                        if parent is None:
                            parent = await bot.fetch_channel(int(parent_channel_id))
                    if parent is not None:
                        approve_channel = parent
                except Exception:
                    approve_channel = interaction.channel
            msg = await approve_channel.send(
                summary[:2000], view=view, allowed_mentions=approve_mentions
            )
            request.approval_channel_id = str(msg.channel.id)
            request.approval_message_id = str(msg.id)
            await _access().store.save_request(request)
            bot = _STATE.get("bot")
            if bot:
                bot.add_view(ApprovalView(request.request_id))
            return "approval_pending"

    if not interaction.response.is_done():
        await interaction.response.defer()

    # Verify retained images still match envelope before submit.
    if not metas_match(envelope.image_metas, metas_from_images(submit_images)):
        raise ValidationError(
            "Image metadata mismatch before submit",
            user_message="Image set no longer matches the approved request; please resubmit.",
        )

    # One-run grant consume happens under the scope lock inside _launch_run.
    await _launch_run(
        interaction,
        prompt_text=prompt_text,
        images=submit_images,
        skipped=skipped,
        agent_id=agent_id,
        force_new=want_new,
        model=envelope.model,
        grant=grant,
        envelope=envelope,
        scope=scope,
        role_ids=role_ids,
        skip_status_post=skip_status_post or (thread_bound and status_msg is not None),
        status_msg=status_msg,
        thread_bound=thread_bound,
        parent_channel_id=parent_channel_id,
        policy_channel_id=pol_ch,
        agent_display_name=agent_display_name,
    )
    return "launched"


# ---------------------------------------------------------------------------
# Interaction routing for persistent buttons
# ---------------------------------------------------------------------------


async def handle_component(interaction: discord.Interaction) -> bool:
    custom_id = (interaction.data or {}).get("custom_id") or ""
    if not custom_id.startswith("c105:"):
        return False
    parts = custom_id.split(":", 2)
    if len(parts) < 3:
        return False
    kind, token = parts[1], parts[2]
    # Button clicks also must ack within ~3s before auth/API work.
    await _defer(interaction, ephemeral=True)

    try:
        if kind.startswith("apr_"):
            mode = {"apr_once": "once", "apr_timed": "timed", "apr_deny": "deny"}[kind]
            minutes = _cfg().access.default_grant_minutes if mode == "timed" else None
            # Before approving: fail closed if requester was demoted / policy revoked.
            if mode in {"once", "timed"}:
                pending_req = await _access().store.get_request(token)
                if pending_req is not None and pending_req.envelope is not None:
                    env = pending_req.envelope
                    try:
                        await _revalidate_run_auth(
                            user_id=env.requester_id,
                            guild_id=env.scope.guild_id,
                            channel_id=env.scope.channel_id,
                            role_ids=await _role_ids_for_user(
                                interaction.guild, env.requester_id
                            ),
                            subcommand=(
                                "new"
                                if pending_req.thread_bound and not env.is_follow_up
                                else "run"
                            ),
                            interaction=interaction,
                            policy_channel_id=resolve_policy_channel_id(
                                channel_id=env.scope.channel_id,
                                parent_channel_id=pending_req.parent_channel_id,
                            ),
                        )
                    except (AuthorizationError, ConfigurationError) as exc:
                        await _access().deny_unauthorized_request(
                            token,
                            actor_id=str(interaction.user.id),
                            reason=exc.user_message,
                        )
                        if interaction.message:
                            try:
                                await interaction.message.edit(
                                    content=(
                                        f"### Denied\nRequest `{token}` — "
                                        f"requester no longer authorized."
                                    ),
                                    view=None,
                                    allowed_mentions=CONTENT_MENTIONS,
                                )
                            except discord.HTTPException:
                                pass
                        await _ephemeral(
                            interaction,
                            f"Cannot approve: {exc.user_message}",
                        )
                        return True
            request = await _access().decide_request(
                interaction.user.id, token, mode=mode, minutes=minutes
            )
            await _ephemeral(
                interaction,
                f"Decision recorded: `{request.decision.value}`.",
            )
            if request.decision.value.startswith("approved"):
                # Auto-launch for the requester using retained images.
                await _launch_approved_request(interaction, request)
            elif request.approval_message_id and interaction.message:
                try:
                    await interaction.message.edit(
                        content=f"### Approval {request.decision.value}\nRequest `{request.request_id}`",
                        view=None,
                        allowed_mentions=CONTENT_MENTIONS,
                    )
                except discord.HTTPException:
                    pass
            return True

        if kind.startswith("idle_"):
            choice = {
                "idle_cont": IdleChoice.CONTINUE,
                "idle_new": IdleChoice.NEW,
                "idle_cancel": IdleChoice.CANCEL,
            }[kind]
            await _complete_idle(interaction, token, choice)
            return True

        if kind.startswith("mdl_"):
            choice = {
                "mdl_new": ModelChoice.NEW_SESSION,
                "mdl_cont": ModelChoice.CONTINUE_ORIGINAL,
                "mdl_cancel": ModelChoice.CANCEL,
            }[kind]
            await _complete_model(interaction, token, choice)
            return True
    except (AuthorizationError, StaleStateError, CursorCloudError) as exc:
        await _ephemeral(interaction, exc.user_message)
        return True
    except Exception:
        logger.exception("Cursor component handler failed")
        await _ephemeral(interaction, "Could not process that control.")
        return True
    return False


async def _launch_approved_request(interaction: discord.Interaction, request) -> None:
    """Launch an approved request only if requester is still authorized."""
    access = _access()
    # Reload — decision path may have raced with expiry/deny.
    request = await access.store.get_request(request.request_id)
    if request is None or not str(request.decision.value).startswith("approved"):
        await _ephemeral(interaction, "Request is not approved.")
        return

    envelope = request.envelope
    scope = envelope.scope
    role_ids = await _role_ids_for_user(interaction.guild, envelope.requester_id)
    early_pol_ch = resolve_policy_channel_id(
        channel_id=scope.channel_id,
        parent_channel_id=request.parent_channel_id,
    )

    try:
        await _revalidate_run_auth(
            user_id=envelope.requester_id,
            guild_id=scope.guild_id,
            channel_id=scope.channel_id,
            role_ids=role_ids,
            subcommand=(
                "new" if request.thread_bound and not envelope.is_follow_up else "run"
            ),
            interaction=interaction,
            policy_channel_id=early_pol_ch,
        )
    except (AuthorizationError, ConfigurationError) as exc:
        await access.deny_unauthorized_request(
            request.request_id,
            actor_id=str(interaction.user.id),
            reason=getattr(exc, "user_message", None) or str(exc),
        )
        if interaction.message:
            try:
                await interaction.message.edit(
                    content=(
                        f"### Denied\nRequest `{request.request_id}` — "
                        f"requester no longer authorized."
                    ),
                    view=None,
                    allowed_mentions=CONTENT_MENTIONS,
                )
            except discord.HTTPException:
                pass
        await _ephemeral(
            interaction,
            f"Approved request can no longer launch: {exc.user_message}",
        )
        return

    images = await access.images.get(request.request_id) or []
    if envelope.image_metas and not images:
        await access.deny_unauthorized_request(
            request.request_id,
            actor_id=str(interaction.user.id),
            reason="images_lost_after_restart",
        )
        await _ephemeral(
            interaction,
            "Approved request images are only kept in memory and do not survive "
            "bot restarts; denied. Please resubmit the run with attachments.",
        )
        return
    if not metas_match(envelope.image_metas, metas_from_images(images)):
        await access.deny_unauthorized_request(
            request.request_id,
            actor_id=str(interaction.user.id),
            reason="image_metadata_mismatch",
        )
        await _ephemeral(
            interaction,
            "Approved request image metadata mismatch; denied. Please resubmit.",
        )
        return

    grant = None
    if request.grant_id:
        grant = await access.store.get_grant(request.grant_id)
        if grant is not None and (grant.revoked or (grant.kind == "once" and grant.consumed)):
            await _ephemeral(interaction, "Request already used or expired.")
            return

    channel = (
        interaction.guild.get_channel(int(envelope.scope.channel_id))
        if interaction.guild
        else None
    )
    if channel is None:
        try:
            channel = await interaction.client.fetch_channel(int(envelope.scope.channel_id))
        except Exception:
            channel = interaction.channel

    class _FakeInteraction:
        def __init__(self):
            self.user = type("U", (), {"id": int(envelope.requester_id), "roles": []})()
            self.guild_id = int(envelope.scope.guild_id)
            self.channel_id = int(envelope.scope.channel_id)
            self.channel = channel
            self.guild = interaction.guild
            self.client = interaction.client
            self.response = _Resp()
            self.followup = channel
            self._msg = None

        async def original_response(self):
            return self._msg

    class _Resp:
        def __init__(self):
            self._done = False

        def is_done(self):
            return self._done

        async def send_message(self, content, **kwargs):
            self._done = True
            msg = await channel.send(content, allowed_mentions=CONTENT_MENTIONS)
            fake._msg = msg
            return msg

        async def defer(self, **kwargs):
            self._done = True

    fake = _FakeInteraction()

    async def _followup_send(content, **kwargs):
        kwargs.pop("wait", False)
        msg = await channel.send(
            content,
            allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS),
        )
        fake._msg = msg
        return msg

    fake.followup.send = _followup_send  # type: ignore

    sessions = _sessions()
    active = await sessions.get_active(scope)
    # Prefer request-carried thread metadata (first /cursor new approval has no
    # session yet), then fall back to an existing bound active session.
    thread_bound = bool(request.thread_bound or (active and active.thread_bound))
    parent_channel_id = (
        request.parent_channel_id
        or (active.parent_channel_id if active else None)
    )
    pol_ch = resolve_policy_channel_id(
        channel_id=scope.channel_id,
        session=active,
        parent_channel_id=parent_channel_id,
    )
    status_msg = None
    status_message_id = request.status_message_id or (
        active.status_message_id if active else None
    )
    if thread_bound and status_message_id:
        try:
            status_msg = await channel.fetch_message(int(status_message_id))
        except Exception:
            status_msg = None

    try:
        # Final auth check immediately before submit (inside _launch_run too).
        await _revalidate_run_auth(
            user_id=envelope.requester_id,
            guild_id=scope.guild_id,
            channel_id=scope.channel_id,
            role_ids=role_ids,
            subcommand="new" if thread_bound and not envelope.is_follow_up else "run",
            interaction=interaction,
            policy_channel_id=pol_ch,
        )
        approved_title = None
        if thread_bound and status_msg is not None:
            approved_title = getattr(status_msg.channel, "name", None)
        await _launch_run(
            fake,  # type: ignore
            prompt_text=envelope.prompt_text,
            images=images,
            skipped=[],
            agent_id=envelope.agent_id,
            force_new=not envelope.is_follow_up,
            model=envelope.model,
            grant=grant,
            envelope=envelope,
            scope=scope,
            role_ids=role_ids,
            thread_bound=thread_bound,
            parent_channel_id=parent_channel_id,
            policy_channel_id=pol_ch,
            skip_status_post=thread_bound and status_msg is not None,
            status_msg=status_msg,
            agent_display_name=approved_title,
        )
        await access.images.discard(request.request_id)
        if interaction.message:
            await interaction.message.edit(
                content=f"### Approved\nRequest `{request.request_id}` launched.",
                view=None,
                allowed_mentions=CONTENT_MENTIONS,
            )
    except (AuthorizationError, ConfigurationError) as exc:
        await access.deny_unauthorized_request(
            request.request_id,
            actor_id=str(interaction.user.id),
            reason=getattr(exc, "user_message", None) or str(exc),
        )
        await _ephemeral(
            interaction,
            f"Approved request can no longer launch: {exc.user_message}",
        )
    except Exception as exc:
        logger.exception("Approved launch failed")
        try:
            await interaction.followup.send(
                f"Approved but launch failed: {getattr(exc, 'user_message', exc)}",
                ephemeral=True,
            )
        except Exception:
            pass


async def _complete_idle(interaction, decision_id: str, choice: IdleChoice) -> None:
    sessions = _sessions()
    decision = await sessions.get_idle_decision(decision_id)
    if decision is None or decision.consumed:
        raise StaleStateError()
    if decision.expires_at and utcnow() >= decision.expires_at:
        raise StaleStateError(user_message="Idle decision expired.")
    if str(interaction.user.id) != decision.scope.user_id:
        raise AuthorizationError()

    pending = await sessions.get_pending_payload(decision_id)
    if not pending or not pending.get("prompt_text"):
        # Fail closed — consume so the control cannot be reused after restart.
        async with sessions.lock_for(decision.scope):
            decision = await sessions.get_idle_decision(decision_id)
            if decision and not decision.consumed:
                decision.consumed = True
                decision.choice = IdleChoice.CANCEL
                await sessions.save_idle_decision(decision)
        await sessions.pop_pending_payload(decision_id)
        raise StaleStateError(
            user_message="Pending run payload missing after restart; please resubmit."
        )

    role_ids = _role_ids(interaction.user)
    try:
        await _revalidate_run_auth(
            user_id=decision.scope.user_id,
            guild_id=decision.scope.guild_id,
            channel_id=decision.scope.channel_id,
            role_ids=role_ids,
            subcommand="run",
            interaction=interaction,
        )
    except (AuthorizationError, ConfigurationError):
        async with sessions.lock_for(decision.scope):
            decision = await sessions.get_idle_decision(decision_id)
            if decision and not decision.consumed:
                decision.consumed = True
                decision.choice = IdleChoice.CANCEL
                await sessions.save_idle_decision(decision)
        await sessions.pop_pending_payload(decision_id)
        if pending.get("retention_key"):
            await _access().images.discard(str(pending["retention_key"]))
        raise

    async with sessions.lock_for(decision.scope):
        decision = await sessions.get_idle_decision(decision_id)
        if decision is None or decision.consumed:
            raise StaleStateError()
        decision.consumed = True
        decision.choice = choice
        await sessions.save_idle_decision(decision)

    pending = await sessions.pop_pending_payload(decision_id) or pending
    await _ephemeral(interaction, f"Idle choice: `{choice.value}`.")
    if choice == IdleChoice.CANCEL:
        if pending.get("retention_key"):
            await _access().images.discard(str(pending["retention_key"]))
        if interaction.message:
            try:
                await interaction.message.edit(content="### Idle — cancelled", view=None)
            except discord.HTTPException:
                pass
        return

    active = await sessions.get_active(decision.scope)
    if active and active.thread_bound and choice == IdleChoice.NEW:
        raise ValidationError(
            user_message="Thread sessions cannot start a new agent in this thread.",
        )

    try:
        images = await _rehydrate_pending_images(pending)
    except ValidationError:
        await _discard_retention_key(pending.get("retention_key"))
        raise
    # Handoff complete — drop process-local retention promptly.
    await _discard_retention_key(pending.get("retention_key"))

    if interaction.message:
        try:
            await interaction.message.edit(
                content=f"### Idle — `{choice.value}`", view=None
            )
        except discord.HTTPException:
            pass

    await _prepare_and_maybe_launch(
        interaction,
        pending.get("prompt") or pending["prompt_text"],
        pending.get("message_ref"),
        [],
        force_new=(choice == IdleChoice.NEW),
        skip_idle=True,
        prebuilt=(
            pending["prompt_text"],
            images,
            list(pending.get("skipped") or []),
        ),
    )


async def _complete_model(interaction, decision_id: str, choice: ModelChoice) -> None:
    sessions = _sessions()
    decision = await sessions.get_model_decision(decision_id)
    if decision is None or decision.consumed:
        raise StaleStateError()
    if decision.expires_at and utcnow() >= decision.expires_at:
        raise StaleStateError(user_message="Model decision expired.")
    if str(interaction.user.id) != decision.scope.user_id:
        raise AuthorizationError()

    pending = await sessions.get_pending_payload(decision_id)
    if not pending or not pending.get("prompt_text"):
        async with sessions.lock_for(decision.scope):
            decision = await sessions.get_model_decision(decision_id)
            if decision and not decision.consumed:
                decision.consumed = True
                decision.choice = ModelChoice.CANCEL
                await sessions.save_model_decision(decision)
        await sessions.pop_pending_payload(decision_id)
        raise StaleStateError(
            user_message="Pending run payload missing after restart; please resubmit."
        )

    role_ids = _role_ids(interaction.user)
    try:
        await _revalidate_run_auth(
            user_id=decision.scope.user_id,
            guild_id=decision.scope.guild_id,
            channel_id=decision.scope.channel_id,
            role_ids=role_ids,
            subcommand="run",
            interaction=interaction,
        )
    except (AuthorizationError, ConfigurationError):
        async with sessions.lock_for(decision.scope):
            decision = await sessions.get_model_decision(decision_id)
            if decision and not decision.consumed:
                decision.consumed = True
                decision.choice = ModelChoice.CANCEL
                await sessions.save_model_decision(decision)
        await sessions.pop_pending_payload(decision_id)
        if pending.get("retention_key"):
            await _access().images.discard(str(pending["retention_key"]))
        raise

    async with sessions.lock_for(decision.scope):
        decision = await sessions.get_model_decision(decision_id)
        if decision is None or decision.consumed:
            raise StaleStateError()
        decision.consumed = True
        decision.choice = choice
        await sessions.save_model_decision(decision)

    pending = await sessions.pop_pending_payload(decision_id) or pending
    await _ephemeral(interaction, f"Model choice: `{choice.value}`.")
    if choice == ModelChoice.CANCEL:
        if pending.get("retention_key"):
            await _access().images.discard(str(pending["retention_key"]))
        if interaction.message:
            try:
                await interaction.message.edit(content="### Model — cancelled", view=None)
            except discord.HTTPException:
                pass
        return

    active = await sessions.get_active(decision.scope)
    if active and active.thread_bound and choice == ModelChoice.NEW_SESSION:
        raise ValidationError(
            user_message="Thread sessions cannot start a new agent in this thread.",
        )

    try:
        images = await _rehydrate_pending_images(pending)
    except ValidationError:
        await _discard_retention_key(pending.get("retention_key"))
        raise
    await _discard_retention_key(pending.get("retention_key"))

    if interaction.message:
        try:
            await interaction.message.edit(
                content=f"### Model — `{choice.value}`", view=None
            )
        except discord.HTTPException:
            pass

    # Re-enter prepare so approval hashing includes the chosen model path.
    await _prepare_and_maybe_launch(
        interaction,
        pending.get("prompt") or pending["prompt_text"],
        pending.get("message_ref"),
        [],
        skip_model=True,
        model_override_choice=choice,
        prebuilt=(
            pending["prompt_text"],
            images,
            list(pending.get("skipped") or []),
        ),
    )


# ---------------------------------------------------------------------------
# Slash command group
# ---------------------------------------------------------------------------

cursor_group = SlashCommandGroup(
    "cursor",
    "Cursor Cloud Agents",
)


@cursor_group.command(name="run", description="Start or continue a Cursor Cloud Agent run")
async def cursor_run(
    ctx: discord.ApplicationContext,
    # Option must be the default (not the annotation): `from __future__ import annotations`
    # stringifies annotations, which breaks py-cord's Option parsing at invoke time.
    prompt: str = Option(str, "Instruction for the agent"),
    message: str = Option(
        str, "Message URL or ID for reply-chain context", required=False
    ),
    image1: discord.Attachment = Option(discord.Attachment, "Image 1", required=False),
    image2: discord.Attachment = Option(discord.Attachment, "Image 2", required=False),
    image3: discord.Attachment = Option(discord.Attachment, "Image 3", required=False),
    image4: discord.Attachment = Option(discord.Attachment, "Image 4", required=False),
    image5: discord.Attachment = Option(discord.Attachment, "Image 5", required=False),
):
    interaction = ctx.interaction
    if await _gate(interaction, "run") is None:
        return
    # Acknowledge before Cursor API / image download work (Discord ~3s limit).
    await _defer(interaction, ephemeral=True)
    try:
        await _prepare_and_maybe_launch(
            interaction,
            prompt,
            message,
            [image1, image2, image3, image4, image5],
        )
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)
    except Exception as exc:
        logger.exception("cursor run failed")
        await _ephemeral(interaction, f"Run failed: {exc}")


def _thread_idle_note() -> str:
    return (
        f"_Note: Discord's minimum thread auto-archive is 60 minutes; "
        f"this bot archives idle sessions after "
        f"{_cfg().session_idle_prompt_minutes} minutes._"
    )


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


def _interaction_shim_from_message(message: discord.Message):
    """Minimal interaction-like object for message-driven Cursor launches.

    Important: do **not** monkey-patch ``message.channel.send`` — that used to
    recurse forever when followup.send aliased the channel itself.
    """

    class _Resp:
        def __init__(self):
            self._done = True

        def is_done(self):
            return True

        async def send_message(self, *a, **k):
            return None

        async def defer(self, **k):
            return None

    # Capture the bound send once. Never assign followup = channel then overwrite
    # channel.send — that recurses (followup.send -> channel.send -> followup.send).
    _channel_send = message.channel.send

    class _Followup:
        async def send(self, content, **kwargs):
            kwargs.pop("wait", None)
            kwargs.pop("ephemeral", None)
            return await _channel_send(
                content,
                allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS),
            )

    class _Shim:
        def __init__(self):
            self.user = message.author
            self.guild_id = message.guild.id if message.guild else 0
            self.channel_id = message.channel.id
            self.channel = message.channel
            self.guild = message.guild
            self.client = _STATE.get("bot")
            self.response = _Resp()
            self.followup = _Followup()
            self.id = message.id
            self._msg = None

        async def original_response(self):
            return self._msg

    return _Shim()


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


async def _start_thread_bound_session(
    *,
    interaction,
    prompt: str,
    message_ref: str | None,
    images: list[discord.Attachment | None],
    parent_channel,
    parent_channel_id: str,
    user,
    guild_id: str | int,
    starter_message: discord.Message | None = None,
    prebuilt: tuple[str, list[ImageInput], list[str]] | None = None,
    notify,
) -> None:
    """Shared `/cursor new` + `$agent` launch: public thread session + Activity."""
    thread_name = await _generate_session_title(prompt)
    thread = None
    activity_msg = None
    try:
        thread = await _create_public_agent_thread(
            parent_channel=parent_channel,
            starter_message=starter_message,
            thread_name=thread_name,
        )
    except discord.Forbidden:
        await notify("Cannot create a public thread here (missing permissions).")
        return
    except discord.HTTPException as exc:
        await notify(f"Could not create thread: {exc}")
        return

    scope = ScopeKey(
        guild_id=str(guild_id or 0),
        channel_id=str(thread.id),
        user_id=str(user.id),
    )
    try:
        activity_msg = await thread.send(
            initial_queued_message(),
            allowed_mentions=CONTENT_MENTIONS,
        )
    except discord.HTTPException as exc:
        await notify(f"Thread created but could not post activity: {exc}")
        try:
            await thread.edit(archived=True, locked=True)
        except Exception:
            logger.debug(
                "Failed to archive orphan Cursor thread %s", thread.id, exc_info=True
            )
        return

    async def _abandon_thread(reason: str) -> None:
        if activity_msg is not None:
            try:
                await activity_msg.edit(
                    content=f"### Error\n{reason}"[:2000],
                    allowed_mentions=CONTENT_MENTIONS,
                )
            except Exception:
                pass
        if thread is not None:
            try:
                await thread.edit(archived=True, locked=True)
            except Exception:
                logger.debug(
                    "Failed to archive orphan Cursor thread %s",
                    thread.id,
                    exc_info=True,
                )

    try:
        outcome = await _prepare_and_maybe_launch(
            interaction,
            prompt,
            message_ref,
            images,
            force_new=True,
            scope_override=scope,
            policy_channel_id=parent_channel_id,
            thread_bound=True,
            parent_channel_id=parent_channel_id,
            status_msg=activity_msg,
            skip_status_post=True,
            auth_subcommand="new",
            prebuilt=prebuilt,
            agent_display_name=thread_name,
        )
        # `$agent` already shows the thread under the start message — no success spam.
        # Slash `/cursor new` still gets a short ephemeral ack (no archive note).
        if outcome == "approval_pending":
            await notify(
                f"Thread {thread.mention} is ready; waiting for approval before launch.\n"
                f"{_thread_idle_note()}"
            )
        elif outcome == "decision_pending":
            await notify(
                f"Thread {thread.mention} is ready; choose how to proceed in-channel."
            )
        elif starter_message is None:
            await notify(f"Started Cursor session in {thread.mention}.")
    except CursorCloudError as exc:
        await _abandon_thread(exc.user_message)
        await notify(exc.user_message)
    except Exception as exc:
        logger.exception("cursor thread session failed")
        await _abandon_thread(str(exc))
        await notify(f"Thread session failed: {exc}")


@cursor_group.command(
    name="new",
    description="Start a Cursor agent in a new public thread (thread = session)",
)
async def cursor_new(
    ctx: discord.ApplicationContext,
    prompt: str = Option(str, "Instruction for the agent"),
    message: str = Option(
        str, "Message URL or ID for reply-chain context", required=False
    ),
    image1: discord.Attachment = Option(discord.Attachment, "Image 1", required=False),
    image2: discord.Attachment = Option(discord.Attachment, "Image 2", required=False),
    image3: discord.Attachment = Option(discord.Attachment, "Image 3", required=False),
    image4: discord.Attachment = Option(discord.Attachment, "Image 4", required=False),
    image5: discord.Attachment = Option(discord.Attachment, "Image 5", required=False),
):
    interaction = ctx.interaction
    if await _gate(interaction, "new") is None:
        return
    if isinstance(interaction.channel, discord.Thread) or _channel_is_thread(
        interaction.channel
    ):
        await _ephemeral(
            interaction,
            "Use `/cursor new` from the parent channel, not inside a thread.",
        )
        return
    await _defer(interaction, ephemeral=True)
    parent_channel_id = str(interaction.channel_id)

    async def _notify(content: str) -> None:
        await _ephemeral(interaction, content)

    await _start_thread_bound_session(
        interaction=interaction,
        prompt=prompt,
        message_ref=message,
        images=[image1, image2, image3, image4, image5],
        parent_channel=interaction.channel,
        parent_channel_id=parent_channel_id,
        user=interaction.user,
        guild_id=interaction.guild_id or 0,
        starter_message=None,
        notify=_notify,
    )


async def handle_agent_prefix(ctx: ext_commands.Context, prompt: str) -> None:
    """`$agent <prompt>` — same as `/cursor new`, rooted on the start message."""
    prompt_text = (prompt or "").strip()
    message = ctx.message
    if not prompt_text and not message.attachments:
        await message.reply(
            "Usage: `$agent <prompt>` (optional image attachments).",
            mention_author=False,
            allowed_mentions=CONTENT_MENTIONS,
        )
        return
    if isinstance(ctx.channel, discord.Thread) or _channel_is_thread(ctx.channel):
        await message.reply(
            "Use `$agent` from the parent channel, not inside a thread.",
            mention_author=False,
            allowed_mentions=CONTENT_MENTIONS,
        )
        return

    cfg = _cfg()
    if cfg is None or not cfg.enabled:
        await message.reply(
            "Cursor commands are disabled.",
            mention_author=False,
            allowed_mentions=CONTENT_MENTIONS,
        )
        return

    parent_channel_id = str(ctx.channel.id)
    try:
        await _revalidate_run_auth(
            user_id=ctx.author.id,
            guild_id=ctx.guild.id if ctx.guild else 0,
            channel_id=ctx.channel.id,
            role_ids=_role_ids(ctx.author),
            subcommand="new",
            interaction=None,
            policy_channel_id=parent_channel_id,
        )
    except CursorCloudError as exc:
        await message.reply(
            exc.user_message[:2000],
            mention_author=False,
            allowed_mentions=CONTENT_MENTIONS,
        )
        return

    shim = _interaction_shim_from_message(message)
    try:
        prebuilt = await _build_context_from_message(
            message, prompt_text or "(see attachments)"
        )
    except Exception:
        logger.exception("cursor $agent context failed")
        await message.reply(
            "Could not build run context from that message.",
            mention_author=False,
            allowed_mentions=CONTENT_MENTIONS,
        )
        return

    async def _notify(content: str) -> None:
        try:
            await message.reply(
                content[:2000],
                mention_author=False,
                allowed_mentions=CONTENT_MENTIONS,
            )
        except discord.HTTPException:
            await ctx.channel.send(content[:2000], allowed_mentions=CONTENT_MENTIONS)

    await _start_thread_bound_session(
        interaction=shim,
        prompt=prompt_text or "(see attachments)",
        message_ref=None,
        images=[],
        parent_channel=ctx.channel,
        parent_channel_id=parent_channel_id,
        user=ctx.author,
        guild_id=ctx.guild.id if ctx.guild else 0,
        starter_message=message,
        prebuilt=prebuilt,
        notify=_notify,
    )


@cursor_group.command(name="stop", description="Cancel your active Cursor run in this channel")
async def cursor_stop(
    ctx: discord.ApplicationContext,
    user: discord.User = Option(
        discord.User,
        "Tier0/1 emergency: stop another user's owned session in this channel",
        required=False,
    ),
):
    interaction = ctx.interaction
    if await _gate(interaction, "stop") is None:
        return
    await _defer(interaction, ephemeral=True)
    actor_scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    target_user_id = str(user.id) if user is not None else actor_scope.user_id
    emergency = user is not None and target_user_id != actor_scope.user_id
    if emergency:
        tier = await _access().resolve_tier(interaction.user.id)
        if tier not in {AccessTier.GOD, AccessTier.ADMIN}:
            await _ephemeral(
                interaction,
                "Only Tier 0/1 may emergency-stop another user's owned session.",
            )
            return
        await _access()._audit(
            interaction.user.id,
            "emergency_stop",
            target_id=target_user_id,
            detail={
                "guild_id": actor_scope.guild_id,
                "channel_id": actor_scope.channel_id,
            },
        )
    scope = ScopeKey(
        guild_id=actor_scope.guild_id,
        channel_id=actor_scope.channel_id,
        user_id=target_user_id,
    )
    async with sessions.lock_for(scope):
        active = await sessions.get_active(scope)
        if active is None or not active.latest_run_id:
            await _ephemeral(interaction, "No active owned run to stop.")
            return
        try:
            await _client().cancel_run(active.agent_id, active.latest_run_id)
            active.latest_run_status = RunStatus.CANCELLED
            await sessions.upsert(active)
            await sessions.touch_activity(scope, active.agent_id)
            prefix = "Emergency cancel" if emergency else "Cancel"
            await _ephemeral(
                interaction,
                f"{prefix} requested for `{active.latest_run_id}` (owner <@{target_user_id}>).",
            )
        except CursorCloudError as exc:
            await _ephemeral(interaction, exc.user_message)


def _format_session_details(session) -> str:
    """Ephemeral session card: run id + git (kept out of thread chat chrome)."""
    lines = [
        "### Session",
        f"Agent: `{session.agent_id}`",
        f"Name: {redact_untrusted(session.name)[:80] or '(unnamed)'}",
        f"State: `{session.latest_run_status.value}`",
    ]
    if session.latest_run_id:
        lines.append(f"Run: `{session.latest_run_id}`")
    if session.model:
        lines.append(f"Model: `{session.model}`")
    if session.thread_bound:
        lines.append("Mode: thread-bound")
        if session.parent_channel_id:
            lines.append(f"Parent: `{session.parent_channel_id}`")
    git_items = list(session.latest_git or [])
    if git_items:
        lines.append("")
        lines.append("### Git")
        for item in git_items[:5]:
            branch = item.get("branch") or "(branch)"
            pr = item.get("pr_url") or item.get("prUrl")
            if pr:
                lines.append(f"- `{branch}` — {pr}")
            else:
                lines.append(f"- `{branch}`")
    return "\n".join(lines)[:2000]


@cursor_group.command(name="sessions", description="List your recent Cursor sessions here")
async def cursor_sessions(ctx: discord.ApplicationContext):
    interaction = ctx.interaction
    if await _gate(interaction, "sessions") is None:
        return
    scope = _scope_from_interaction(interaction)
    items = await _sessions().list_sessions(scope)
    if not items:
        await _ephemeral(interaction, "No owned sessions in this channel.")
        return
    lines = ["### Sessions"]
    for s in items:
        mark = " (active)" if s.active else ""
        run = f" run `{s.latest_run_id}`" if s.latest_run_id else ""
        git_bits = []
        for item in list(s.latest_git or [])[:2]:
            if item.get("branch"):
                git_bits.append(str(item["branch"]))
        git = f" git `{', '.join(git_bits)}`" if git_bits else ""
        lines.append(
            f"- `{s.agent_id}` {redact_untrusted(s.name)[:40]} "
            f"[{s.latest_run_status.value}]{run}{git}{mark}"
        )
    await _ephemeral(interaction, "\n".join(lines)[:2000])


@cursor_group.command(
    name="session",
    description="Show active session details, or switch to an owned agent id",
)
async def cursor_session(
    ctx: discord.ApplicationContext,
    agent_id: str = Option(
        str,
        "Owned agent id (omit to show the active session)",
        required=False,
    ),
):
    interaction = ctx.interaction
    if await _gate(interaction, "session") is None:
        return
    await _defer(interaction, ephemeral=True)
    scope = _scope_from_interaction(interaction)
    try:
        sessions = _sessions()
        active = await sessions.get_active(scope)
        target = (agent_id or "").strip()
        if not target:
            if active is None:
                await _ephemeral(interaction, "No active owned session here.")
                return
            await _ephemeral(interaction, _format_session_details(active))
            return

        # Validate ownership locally first — never expose org-wide agents.
        if active is not None and active.thread_bound and active.agent_id != target:
            await _ephemeral(
                interaction,
                "This thread is bound to a single Cursor session; agent switching is disabled.",
            )
            return
        session = await sessions.get_session(scope, target)
        if session is None:
            raise OwnershipError()
        if session.thread_bound and active is not None and active.agent_id != target:
            await _ephemeral(
                interaction,
                "This thread is bound to a single Cursor session; agent switching is disabled.",
            )
            return
        # Optional API check that it still exists.
        try:
            await _client().get_agent(target)
        except CursorCloudError:
            pass
        await sessions.set_active(scope, target)
        await sessions.touch_activity(scope, target)
        refreshed = await sessions.get_session(scope, target) or session
        await _ephemeral(
            interaction,
            f"Active session set to `{target}`.\n\n{_format_session_details(refreshed)}",
        )
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@cursor_group.command(name="model", description="Show or set preferred model for next new session")
async def cursor_model(
    ctx: discord.ApplicationContext,
    model_id: str = Option(str, "Model id from /v1/models", required=False),
):
    interaction = ctx.interaction
    if await _gate(interaction, "model") is None:
        return
    await _defer(interaction, ephemeral=True)
    scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    if not model_id:
        try:
            models = await _client().list_models()
        except CursorCloudError as exc:
            await _ephemeral(interaction, exc.user_message)
            return
        active = await sessions.get_active(scope)
        preferred = (
            (active.preferred_model if active else None)
            or await sessions.get_model_pref(scope)
            or _cfg().default_model
            or "(default)"
        )
        lines = [
            "### Model",
            f"Preferred for next **new** session: `{preferred}`",
            "Note: follow-up runs cannot change an agent's create-time model.",
            "",
            "Available:",
        ]
        for m in models[:15]:
            lines.append(f"- `{m.id}` {m.display_name}")
        await _ephemeral(interaction, "\n".join(lines)[:2000])
        return

    try:
        models = await _client().list_models()
        valid = {m.id for m in models}
        for m in models:
            valid.update(m.aliases)
        if model_id not in valid:
            await _ephemeral(interaction, f"Unknown model `{model_id}`.")
            return
        await sessions.set_model_pref(scope, model_id)
        active = await sessions.get_active(scope)
        if active is not None:
            active.preferred_model = model_id
            await sessions.upsert(active)
            await sessions.touch_activity(scope, active.agent_id)
        await _ephemeral(
            interaction,
            f"Preferred model set to `{model_id}`. "
            "It applies when you start a **new** session; follow-ups keep the original model.",
        )
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@cursor_group.command(
    name="history",
    description="Show local activity log for a Cursor run (thinking/tools/result)",
)
async def cursor_history(
    ctx: discord.ApplicationContext,
    run_id: str = Option(
        str,
        "Run id (default: active run)",
        required=False,
    ),
    page: int = Option(
        int,
        "Page number (1-based)",
        required=False,
    ),
    verbose: bool = Option(
        bool,
        "Include status/system noise (default: tools/thinking/result only)",
        required=False,
        default=False,
    ),
):
    interaction = ctx.interaction
    if await _gate(interaction, "history") is None:
        return
    await _defer(interaction, ephemeral=True)
    scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    active = await sessions.get_active(scope)
    target_run = (run_id or "").strip() or (active.latest_run_id if active else None)
    if not target_run:
        await _ephemeral(interaction, "No active run. Pass `run_id` or start a run first.")
        return
    page_num = max(1, int(page or 1))
    page_size = 12
    logs = _run_logs()
    kinds = None if verbose else HISTORY_FOCUS_KINDS
    total = await logs.entry_count(scope, target_run, kinds=kinds)
    if total == 0:
        # Soft hint: list recent run ids if any.
        recent = await logs.list_run_ids(scope)
        hint = ""
        if recent:
            shown = ", ".join(f"`{r}`" for r in recent[:5])
            hint = f"\nRecent logged runs: {shown}"
        await _ephemeral(
            interaction,
            f"### History\nNo log entries for `{target_run}`.{hint}",
        )
        return
    offset = (page_num - 1) * page_size
    entries = await logs.get_entries(
        scope, target_run, offset=offset, limit=page_size, kinds=kinds
    )
    text = format_history_message(
        entries,
        run_id=target_run,
        page=page_num,
        total_entries=total,
        page_size=page_size,
        agent_id=active.agent_id if active else None,
    )
    await _ephemeral(interaction, text)


@cursor_group.command(name="status", description="Show status for your active Cursor run")
async def cursor_status(
    ctx: discord.ApplicationContext,
    user: discord.User = Option(
        discord.User,
        "Tier0/1 emergency: status for another user's owned session in this channel",
        required=False,
    ),
):
    interaction = ctx.interaction
    if await _gate(interaction, "status") is None:
        return
    await _defer(interaction, ephemeral=True)
    actor_scope = _scope_from_interaction(interaction)
    target_user_id = str(user.id) if user is not None else actor_scope.user_id
    emergency = user is not None and target_user_id != actor_scope.user_id
    if emergency:
        tier = await _access().resolve_tier(interaction.user.id)
        if tier not in {AccessTier.GOD, AccessTier.ADMIN}:
            await _ephemeral(
                interaction,
                "Only Tier 0/1 may emergency-status another user's owned session.",
            )
            return
        await _access()._audit(
            interaction.user.id,
            "emergency_status",
            target_id=target_user_id,
            detail={
                "guild_id": actor_scope.guild_id,
                "channel_id": actor_scope.channel_id,
            },
        )
    scope = ScopeKey(
        guild_id=actor_scope.guild_id,
        channel_id=actor_scope.channel_id,
        user_id=target_user_id,
    )
    active = await _sessions().get_active(scope)
    if active is None or not active.latest_run_id:
        await _ephemeral(interaction, "No active owned session/run.")
        return
    try:
        run = await _client().get_run(active.agent_id, active.latest_run_id)
        active.latest_run_status = run.status
        git_payload = run.git if isinstance(run.git, dict) else None
        if git_payload:
            branches = []
            for item in git_payload.get("branches") or []:
                if isinstance(item, dict):
                    branches.append(
                        {
                            "repo_url": str(
                                item.get("repoUrl") or item.get("repo_url") or ""
                            ),
                            "branch": item.get("branch"),
                            "pr_url": item.get("prUrl") or item.get("pr_url"),
                        }
                    )
            if branches:
                active.latest_git = branches
        await _sessions().upsert(active)
        await _sessions().touch_activity(scope, active.agent_id)
        text = (
            f"### Status\n"
            f"Owner: <@{target_user_id}>\n"
            f"Agent: `{active.agent_id}`\n"
            f"Run: `{run.id}`\n"
            f"State: `{run.status.value}`\n"
        )
        if active.latest_git:
            text += "\n### Git\n"
            for item in active.latest_git[:5]:
                branch = item.get("branch") or "(branch)"
                pr = item.get("pr_url")
                text += f"- `{branch}`" + (f" — {pr}" if pr else "") + "\n"
        if run.result:
            text += f"\n{redact_untrusted(run.result)[:1500]}"
        # Try edit existing status message
        if active.status_channel_id and active.status_message_id:
            try:
                channel = (
                    interaction.guild.get_channel(int(active.status_channel_id))
                    if interaction.guild
                    else interaction.channel
                )
                if channel:
                    msg = await channel.fetch_message(int(active.status_message_id))
                    await msg.edit(content=text[:2000], allowed_mentions=CONTENT_MENTIONS)
                    await _ephemeral(interaction, "Status message updated.")
                    return
            except Exception:
                pass
        await _public(interaction, text)
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


access_group = cursor_group.create_subgroup("access", "God-only Cursor access management")


@access_group.command(name="list", description="List Cursor tier assignments")
async def cursor_access_list(ctx: discord.ApplicationContext):
    interaction = ctx.interaction
    if await _gate(interaction, "access") is None:
        return
    try:
        await _access().require_god(interaction.user.id)
        data = await _access().list_assignments()
        lines = [
            "### Cursor access",
            f"God: `{data['god']}`",
            f"File Tier1: {', '.join(data['file_tier1']) or '(none)'}",
            f"File Tier2: {', '.join(data['file_tier2']) or '(none)'}",
            "Overlay:",
        ]
        for uid, val in (data["overlay"] or {}).items():
            lines.append(f"- `{uid}` → {val}")
        await _ephemeral(interaction, "\n".join(lines)[:2000])
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@access_group.command(name="set", description="Set a user's Cursor tier (God only)")
async def cursor_access_set(
    ctx: discord.ApplicationContext,
    user: discord.User = Option(discord.User, "Target user"),
    tier: str = Option(str, "1, 2, 3, or reset"),
):
    interaction = ctx.interaction
    if await _gate(interaction, "access") is None:
        return
    try:
        resulting = await _access().set_user_tier(interaction.user.id, user.id, tier)
        await _ephemeral(
            interaction, f"Set <@{user.id}> effective tier intent → `{int(resulting)}` / {tier}."
        )
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@access_group.command(name="grants", description="List active Cursor grants")
async def cursor_access_grants(ctx: discord.ApplicationContext):
    interaction = ctx.interaction
    if await _gate(interaction, "access") is None:
        return
    try:
        await _access().require_god(interaction.user.id)
        grants = await _access().store.list_grants()
        lines = ["### Grants"]
        for g in grants[-30:]:
            if g.revoked or g.consumed:
                continue
            lines.append(
                f"- `{g.grant_id}` {g.kind} user `{g.user_id}` "
                f"scope `{g.scope.as_str()}`"
            )
        await _ephemeral(interaction, "\n".join(lines)[:2000])
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@access_group.command(name="revoke", description="Revoke a Cursor grant (God only)")
async def cursor_access_revoke(
    ctx: discord.ApplicationContext,
    grant_id: str = Option(str, "Grant id"),
):
    interaction = ctx.interaction
    if await _gate(interaction, "access") is None:
        return
    try:
        await _access().revoke_grant(interaction.user.id, grant_id)
        await _ephemeral(interaction, f"Revoked `{grant_id}`.")
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@cursor_group.command(name="approve", description="Approve a pending Tier 2 Cursor request")
async def cursor_approve(
    ctx: discord.ApplicationContext,
    request_id: str = Option(str, "Approval request id"),
    mode: str = Option(str, "once or timed", choices=["once", "timed"]),
    minutes: int = Option(int, "Timed grant minutes", required=False),
):
    interaction = ctx.interaction
    if await _gate(interaction, "approve") is None:
        return
    try:
        # Approvers may be Tier0/1 even if can_use_command blocks tier2 approve name —
        # re-check approver explicitly.
        await _access().require_approver(interaction.user.id)
        pending_req = await _access().store.get_request(request_id)
        if pending_req is not None and pending_req.envelope is not None:
            env = pending_req.envelope
            try:
                await _revalidate_run_auth(
                    user_id=env.requester_id,
                    guild_id=env.scope.guild_id,
                    channel_id=env.scope.channel_id,
                    role_ids=await _role_ids_for_user(
                        interaction.guild, env.requester_id
                    ),
                    subcommand="run",
                    interaction=interaction,
                )
            except (AuthorizationError, ConfigurationError) as exc:
                await _access().deny_unauthorized_request(
                    request_id,
                    actor_id=str(interaction.user.id),
                    reason=exc.user_message,
                )
                await _ephemeral(
                    interaction, f"Cannot approve: {exc.user_message}"
                )
                return
        request = await _access().decide_request(
            interaction.user.id, request_id, mode=mode, minutes=minutes
        )
        await _ephemeral(interaction, f"Request `{request_id}` → `{request.decision.value}`.")
        if request.decision.value.startswith("approved"):
            await _launch_approved_request(interaction, request)
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@cursor_group.command(name="deny", description="Deny a pending Tier 2 Cursor request")
async def cursor_deny(
    ctx: discord.ApplicationContext,
    request_id: str = Option(str, "Approval request id"),
):
    interaction = ctx.interaction
    if await _gate(interaction, "deny") is None:
        return
    try:
        await _access().require_approver(interaction.user.id)
        request = await _access().decide_request(
            interaction.user.id, request_id, mode="deny"
        )
        await _ephemeral(interaction, f"Request `{request_id}` → `{request.decision.value}`.")
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def _register_prefix_commands(bot: discord.Bot) -> None:
    """Register `$agent` (message-rooted `/cursor new`) on the prefix command bot."""
    if getattr(bot, "_cursor_agent_prefix_registered", False):
        return
    if not hasattr(bot, "add_command") or not hasattr(bot, "get_command"):
        logger.warning("Cursor $agent prefix skipped: bot has no prefix command API")
        return
    if bot.get_command("agent") is not None:
        bot._cursor_agent_prefix_registered = True
        return

    @ext_commands.command(
        name="agent",
        help="Start a Cursor agent thread from this message (same as /cursor new).",
    )
    async def agent_prefix_command(
        ctx: ext_commands.Context, *, prompt: str = ""
    ) -> None:
        await handle_agent_prefix(ctx, prompt)

    bot.add_command(agent_prefix_command)
    bot._cursor_agent_prefix_registered = True
    logger.info("Registered Cursor prefix command $agent")


def _register_commands(bot: discord.Bot) -> None:
    # Avoid duplicate slash registration across reconnects / repeated ready.
    pending = list(getattr(bot, "pending_application_commands", []) or [])
    attached = list(getattr(bot, "application_commands", []) or [])
    has_cursor = any(getattr(cmd, "name", None) == "cursor" for cmd in pending + attached)
    if not has_cursor:
        bot.add_application_command(cursor_group)
    _register_prefix_commands(bot)


async def _pending_rehydratable(pending: dict[str, Any] | None) -> bool:
    """Text-only pending survives restart; multimodal needs process-local bytes."""
    if not pending or not pending.get("prompt_text"):
        return False
    key = pending.get("retention_key")
    metas = list(pending.get("image_metas") or [])
    if not key and not metas:
        return True
    if not key:
        return False
    access = _STATE.get("access")
    if access is None:
        return False
    images = await access.images.get(str(key))
    return bool(images)


async def _register_views(bot: discord.Bot) -> None:
    """Re-register durable non-ephemeral views; skip consumed/expired/unrehydratable."""
    access = _STATE.get("access")
    sessions = _STATE.get("sessions")
    now = utcnow()
    if access:
        for request in await access.store.list_requests():
            if request.decision.value == "pending":
                # Multimodal approvals need process-local retained bytes.
                images = await access.images.get(request.request_id)
                if request.envelope.image_metas and not images:
                    # Fail closed after restart: do not reattach dead multimodal UI.
                    continue
                bot.add_view(ApprovalView(request.request_id))
    if sessions:
        state = sessions.export_state()
        for decision_id, raw in (state.get("idle") or {}).items():
            try:
                decision = IdleDecision.from_dict(raw)
            except Exception:
                continue
            if decision.consumed:
                continue
            if decision.expires_at and now >= decision.expires_at:
                continue
            pending = await sessions.get_pending_payload(decision_id)
            if not await _pending_rehydratable(pending):
                continue
            bot.add_view(IdleDecisionView(decision_id))
        for decision_id, raw in (state.get("model") or {}).items():
            try:
                decision = ModelDecision.from_dict(raw)
            except Exception:
                continue
            if decision.consumed:
                continue
            if decision.expires_at and now >= decision.expires_at:
                continue
            pending = await sessions.get_pending_payload(decision_id)
            if not await _pending_rehydratable(pending):
                continue
            bot.add_view(ModelDecisionView(decision_id))
    _STATE["views_registered"] = True


async def _reconcile_runs() -> None:
    client = _STATE.get("client")
    sessions = _STATE.get("sessions")
    if not client or not sessions:
        return
    for session in await sessions.all_sessions():
        if not session.latest_run_id:
            continue
        if not run_is_busy(session.latest_run_status):
            continue
        try:
            run = await client.get_run(session.agent_id, session.latest_run_id)
            session.latest_run_status = run.status
            await sessions.upsert(session)
            if run.status.is_active:
                bot = _STATE.get("bot")
                if not bot or not session.status_channel_id or not session.status_message_id:
                    continue
                try:
                    channel = bot.get_channel(int(session.status_channel_id))
                    if channel is None:
                        channel = await bot.fetch_channel(int(session.status_channel_id))
                    msg = await channel.fetch_message(int(session.status_message_id))
                except Exception:
                    if session.thread_bound:
                        try:
                            channel = bot.get_channel(int(session.scope.channel_id))
                            if channel is None:
                                channel = await bot.fetch_channel(int(session.scope.channel_id))
                            msg = await channel.send(
                                initial_queued_message(),
                                allowed_mentions=CONTENT_MENTIONS,
                            )
                            session.status_channel_id = str(channel.id)
                            session.status_message_id = str(msg.id)
                            session.degraded = True
                            await sessions.upsert(session)
                        except Exception:
                            session.degraded = True
                            await sessions.upsert(session)
                            continue
                    else:
                        session.degraded = True
                        await sessions.upsert(session)
                        continue

                if session.thread_bound:
                    sink = ThreadActivitySink(
                        msg.channel,
                        msg,
                        edit_interval_ms=_cfg().status_edit_interval_ms,
                        allowed_mentions=CONTENT_MENTIONS,
                    )
                else:
                    sink = DiscordStatusSink(msg)
                tracker = RunTracker(
                    client,
                    sink,
                    edit_interval_ms=_cfg().status_edit_interval_ms,
                    agent_name=session.name or session.agent_id,
                    run_log=_run_logs(),
                    scope=session.scope,
                )

                async def _resume(sess=session, tr=tracker):
                    snap = await tr.track(
                        sess.agent_id,
                        sess.latest_run_id,
                        initial_status=sess.latest_run_status,
                    )
                    sess.latest_run_status = snap.status
                    if snap.status.is_terminal:
                        branches = list(getattr(snap, "git_branches", None) or [])
                        if branches:
                            sess.latest_git = [
                                g.to_dict() if hasattr(g, "to_dict") else dict(g)
                                for g in branches
                            ]
                    await sessions.upsert(sess)

                _STATE["trackers"][session.agent_id] = asyncio.create_task(_resume())
        except Exception:
            logger.exception("Cursor reconcile failed for %s", session.agent_id)


async def _edit_approval_expired_message(request) -> None:
    bot = _STATE.get("bot")
    if not bot or not request.approval_channel_id or not request.approval_message_id:
        return
    try:
        channel = bot.get_channel(int(request.approval_channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(request.approval_channel_id))
        msg = await channel.fetch_message(int(request.approval_message_id))
        await msg.edit(
            content=f"### Expired\nRequest `{request.request_id}` expired.",
            view=None,
            allowed_mentions=CONTENT_MENTIONS,
        )
    except Exception:
        logger.debug(
            "Could not edit expired approval message %s",
            request.request_id,
            exc_info=True,
        )


async def _edit_decision_expired_message(
    *,
    kind: str,
    decision_id: str,
    channel_id: str | None,
    message_id: str | None,
) -> None:
    """Best-effort disable/edit idle or model decision channel message."""
    bot = _STATE.get("bot")
    if not bot or not channel_id or not message_id:
        return
    label = "Idle session" if kind == "idle" else "Model choice"
    try:
        channel = bot.get_channel(int(channel_id))
        if channel is None:
            channel = await bot.fetch_channel(int(channel_id))
        msg = await channel.fetch_message(int(message_id))
        await msg.edit(
            content=f"### Expired\n{label} `{decision_id}` expired.",
            view=None,
            allowed_mentions=CONTENT_MENTIONS,
        )
    except Exception:
        logger.debug(
            "Could not edit expired %s decision message %s",
            kind,
            decision_id,
            exc_info=True,
        )


async def _expire_stale_decisions() -> None:
    """Expire idle/model decisions and discard their retention keys promptly."""
    sessions = _STATE.get("sessions")
    access = _STATE.get("access")
    if not sessions:
        return
    now = utcnow()
    state = sessions.export_state()
    for decision_id, raw in list((state.get("idle") or {}).items()):
        try:
            decision = IdleDecision.from_dict(raw)
        except Exception:
            continue
        if decision.consumed:
            continue
        if decision.expires_at and now >= decision.expires_at:
            decision.consumed = True
            decision.choice = IdleChoice.CANCEL
            await sessions.save_idle_decision(decision)
            pending = await sessions.pop_pending_payload(decision_id)
            if pending:
                await _discard_retention_key(pending.get("retention_key"))
            await _edit_decision_expired_message(
                kind="idle",
                decision_id=decision_id,
                channel_id=decision.message_channel_id,
                message_id=decision.message_id,
            )
    for decision_id, raw in list((state.get("model") or {}).items()):
        try:
            decision = ModelDecision.from_dict(raw)
        except Exception:
            continue
        if decision.consumed:
            continue
        if decision.expires_at and now >= decision.expires_at:
            decision.consumed = True
            decision.choice = ModelChoice.CANCEL
            await sessions.save_model_decision(decision)
            pending = await sessions.pop_pending_payload(decision_id)
            if pending:
                await _discard_retention_key(pending.get("retention_key"))
            await _edit_decision_expired_message(
                kind="model",
                decision_id=decision_id,
                channel_id=decision.message_channel_id,
                message_id=decision.message_id,
            )
    if access:
        await access.images.purge_expired()


async def _archive_idle_threads() -> None:
    """Archive bound threads after session idle (Discord min native archive is 60m)."""
    cfg = _cfg()
    sessions = _sessions()
    bot = _STATE.get("bot")
    if not cfg or not sessions or not bot:
        return
    for session in await sessions.all_sessions():
        if not session.thread_bound:
            continue
        if run_is_busy(session.latest_run_status):
            continue
        if not session_is_idle(session, idle_minutes=cfg.session_idle_prompt_minutes):
            continue
        try:
            channel = bot.get_channel(int(session.scope.channel_id))
            if channel is None:
                channel = await bot.fetch_channel(int(session.scope.channel_id))
            if isinstance(channel, discord.Thread) and not channel.archived:
                await channel.edit(archived=True)
            elif _channel_is_thread(channel) and not getattr(channel, "archived", False):
                await channel.edit(archived=True)
        except Exception:
            logger.debug(
                "Could not auto-archive idle Cursor thread %s",
                session.scope.channel_id,
                exc_info=True,
            )


async def _expiry_loop() -> None:
    while True:
        try:
            if _STATE.get("access"):
                expired = await _access().expire_stale_requests()
                for request in expired:
                    await _edit_approval_expired_message(request)
            await _expire_stale_decisions()
            await _archive_idle_threads()
        except Exception:
            logger.exception("Cursor approval expiry loop failed")
        await asyncio.sleep(60)


async def cleanup_cursor_runtime() -> None:
    """Cancel trackers/tasks and close shared HTTP clients (idempotent)."""
    if _STATE.get("_cleanup_done"):
        return
    _STATE["_cleanup_done"] = True
    to_await: list[asyncio.Task] = []
    for key in ("expiry_task", "reconcile_task"):
        task = _STATE.get(key)
        if task is not None:
            task.cancel()
            to_await.append(task)
            _STATE[key] = None
    for agent_id, task in list((_STATE.get("trackers") or {}).items()):
        task.cancel()
        to_await.append(task)
        _STATE["trackers"].pop(agent_id, None)
    if to_await:
        await asyncio.gather(*to_await, return_exceptions=True)
    client = _STATE.get("client")
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            logger.exception("Cursor client close failed")
        _STATE["client"] = None
    cdn = _STATE.get("cdn")
    if cdn is not None:
        try:
            await cdn.aclose()
        except Exception:
            logger.exception("Cursor CDN client close failed")
        _STATE["cdn"] = None
    _STATE["views_registered"] = False


@MANAGER.builder
def cursor(sonata: AI_Manager):
    cfg = load_cursor_config(CONTEXT.plugin_config)
    _STATE["config"] = cfg

    class Cursor:
        def __init__(self):
            self.config = cfg

        def ready(self):
            return self.config.is_ready

        def readiness_error(self):
            return self.config.readiness_error()

        async def setup(self, bot: discord.Bot):
            await setup_cursor_runtime(sonata, bot)

        async def cleanup(self):
            """Invoked from SonataClient.close() — real shutdown path."""
            await cleanup_cursor_runtime()

    return Cursor


@MANAGER.with_context(manager=True, client=True, config=True)
def cursor_register(context):
    """Register slash commands before first py-cord auto-sync (extend-time)."""
    bot = context.client
    sonata = context.manager
    cfg = load_cursor_config(CONTEXT.plugin_config)
    _STATE["config"] = cfg
    if hasattr(sonata, "cursor"):
        sonata.cursor.config = cfg
    _STATE["bot"] = bot
    setattr(bot, "sonata", sonata)
    _register_commands(bot)

    if not getattr(bot, "_cursor_component_hook", False):

        @bot.listen("on_interaction")
        async def _cursor_interaction(interaction: discord.Interaction):
            if interaction.type != discord.InteractionType.component:
                return
            await handle_component(interaction)

        bot._cursor_component_hook = True

    if not getattr(bot, "_cursor_thread_message_hook", False):

        @bot.listen("on_message")
        async def _cursor_thread_message(message: discord.Message):
            try:
                await handle_thread_message(message)
            except Exception:
                logger.exception("Cursor thread message handler failed")

        bot._cursor_thread_message_hook = True


async def setup_cursor_runtime(sonata: AI_Manager, bot: discord.Bot) -> None:
    cfg = load_cursor_config(CONTEXT.plugin_config)
    _STATE["config"] = cfg
    _STATE["bot"] = bot
    setattr(bot, "sonata", sonata)
    _register_commands(bot)

    if not cfg.enabled:
        logger.info("Cursor plugin disabled")
        return

    if cfg.readiness_error():
        logger.warning("Cursor plugin not ready: %s", cfg.readiness_error())

    beacon = None
    try:
        beacon = sonata.beacon
    except Exception:
        beacon = None

    if beacon is not None:
        branch = beacon.branch("cursor")
        sessions = BeaconSessionStore(
            branch.branch("sessions"), max_recent=cfg.max_recent_sessions
        )
        access_store = BeaconAccessStore(
            branch.branch("access"), audit_limit=cfg.access.audit_history_limit
        )
        run_logs = BeaconRunLogStore(branch.branch("run_logs"))
    else:
        sessions = MemorySessionStore(max_recent=cfg.max_recent_sessions)
        access_store = MemoryAccessStore(audit_limit=cfg.access.audit_history_limit)
        run_logs = MemoryRunLogStore()

    _STATE["sessions"] = sessions
    _STATE["run_logs"] = run_logs
    _STATE["access_store"] = access_store
    _STATE["access"] = AccessController(
        cfg,
        access_store,
        image_retention=ImageRetentionStore(max_total_bytes=cfg.max_retained_image_bytes),
    )
    old = _STATE.get("client")
    _STATE["client"] = CursorCloudClient(cfg)
    if old is not None:
        try:
            await old.aclose()
        except Exception:
            pass

    old_cdn = _STATE.get("cdn")
    _STATE["cdn"] = DiscordCDNDownloader(max_bytes=cfg.max_image_bytes)
    if old_cdn is not None:
        try:
            await old_cdn.aclose()
        except Exception:
            pass

    await _register_views(bot)
    # Expose cleanup for SonataClient.close() (py-cord does not dispatch on_close).
    _STATE["_cleanup_done"] = False
    setattr(bot, "_cursor_cleanup", cleanup_cursor_runtime)
    if hasattr(sonata, "cursor") and sonata.cursor is not None:
        # Ensure builder instance exposes cleanup even if rebuilt.
        if not hasattr(sonata.cursor, "cleanup"):
            sonata.cursor.cleanup = cleanup_cursor_runtime  # type: ignore

    if cfg.is_ready:
        if _STATE.get("reconcile_task") is None or _STATE["reconcile_task"].done():
            _STATE["reconcile_task"] = asyncio.create_task(_reconcile_runs())
        if _STATE.get("expiry_task") is None or _STATE["expiry_task"].done():
            _STATE["expiry_task"] = asyncio.create_task(_expiry_loop())


async def cursor_bot_hook(sonata: AI_Manager, bot: discord.Bot) -> None:
    """Invoked from SonataClient.on_ready for runtime/Beacon setup."""
    await setup_cursor_runtime(sonata, bot)


async def cursor_cleanup_hook(sonata=None, bot=None):
    """Memory-registered cleanup callable for Sonata.get('cursor', 'cleanup')."""
    await cleanup_cursor_runtime()


@MANAGER.mem(
    {},
    key="cursor",
    hook=cursor_bot_hook,
    cleanup=cursor_cleanup_hook,
)
def init_cursor(_M):
    return None
