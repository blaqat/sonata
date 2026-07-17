"""
Cursor Commands
---------------
Discord slash-command adapter for Cursor Cloud Agents (`/cursor …`).

Core API/session/access logic lives in ``cursor_cloud``; this plugin only wires
Discord interactions, channel policies, and Beacon persistence.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import discord
from discord.commands import Option, SlashCommandGroup

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
    parse_message_reference,
)
from cursor_cloud.errors import (
    AuthorizationError,
    BusyRunError,
    CursorCloudError,
    GrantConsumedError,
    OwnershipError,
    StaleStateError,
)
from cursor_cloud.models import (
    AccessTier,
    AgentSession,
    IdleChoice,
    IdleDecision,
    ImageInput,
    ModelChoice,
    ModelDecision,
    RunRequestEnvelope,
    RunStatus,
    ScopeKey,
    utcnow,
)
from cursor_cloud.run_tracker import RunTracker
from cursor_cloud.session_store import (
    MemorySessionStore,
    run_is_busy,
    session_is_idle,
)
from cursor_cloud.status_renderer import initial_queued_message, redact_untrusted
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
    "sessions": None,
    "access_store": None,
    "access": None,
    "bot": None,
    "trackers": {},
    "views_registered": False,
    "sync_done": False,
    "pending_images": {},  # request_id -> list[ImageInput] also in ImageRetentionStore
}


CONTENT_MENTIONS = discord.AllowedMentions(
    everyone=False, users=False, roles=False, replied_user=False
)


def _cfg():
    return _STATE["config"]


def _sessions() -> MemorySessionStore:
    return _STATE["sessions"]


def _access() -> AccessController:
    return _STATE["access"]


def _client() -> CursorCloudClient:
    return _STATE["client"]


def _scope_from_interaction(interaction: discord.Interaction) -> ScopeKey:
    guild_id = str(interaction.guild_id or 0)
    channel_id = str(interaction.channel_id or 0)
    user_id = str(interaction.user.id)
    return ScopeKey(guild_id=guild_id, channel_id=channel_id, user_id=user_id)


def _role_ids(user: discord.abc.User) -> list[str]:
    roles = getattr(user, "roles", None) or []
    return [str(r.id) for r in roles]


async def _policy_allowed(interaction: discord.Interaction, subcommand: str) -> bool:
    bot = _STATE.get("bot")
    sonata = getattr(bot, "sonata", None) if bot else None
    # Prefer AI manager chat.policy_manager via CONTEXT if available.
    policy_manager = None
    try:
        from modules.plugins import PLUGINS_DICT

        chat = PLUGINS_DICT.get("chat")
        # Sonata instance is attached during extend; fall back via MANAGER
    except Exception:
        pass

    # Resolve via interaction.client + AI_Manager singleton pattern used elsewhere.
    sona = None
    client = interaction.client
    if hasattr(client, "sonata"):
        sona = client.sonata
    else:
        # index.py binds Sonata globally through plugins; look up chat on CONTEXT manager host
        try:
            from index import Sonata as SonaGlobal  # type: ignore

            sona = SonaGlobal
        except Exception:
            sona = None

    if sona is not None:
        chat = sona.get("chat") if hasattr(sona, "get") else None
        policy_manager = getattr(chat, "policy_manager", None) if chat else None

    if policy_manager is None:
        return True

    guild_id = interaction.guild_id
    channel_id = interaction.channel_id
    user_id = interaction.user.id
    roles = _role_ids(interaction.user)
    if not policy_manager.can_speak(
        guild_id=guild_id,
        channel_id=channel_id,
        user_id=user_id,
        role_ids=roles,
    ):
        return False
    return policy_manager.is_command_allowed(
        guild_id=guild_id,
        channel_id=channel_id,
        command=f"cursor.{subcommand}",
        user_id=user_id,
        role_ids=roles,
    )


async def _gate(interaction: discord.Interaction, subcommand: str) -> AccessTier | None:
    """Tier then policy. Returns tier or None after responding with denial."""
    cfg = _cfg()
    if cfg is None or not cfg.enabled:
        await _ephemeral(interaction, "Cursor commands are disabled.")
        return None
    err = cfg.readiness_error()
    if err and subcommand not in {"status"}:
        # Still allow god to see status-ish errors; otherwise fail closed.
        if not cfg.god_user_id:
            await _ephemeral(interaction, err)
            return None
        if str(interaction.user.id) != cfg.god_user_id and err:
            await _ephemeral(interaction, err)
            return None

    try:
        tier = await _access().resolve_tier(interaction.user.id)
    except Exception:
        tier = AccessTier.DENIED

    if tier == AccessTier.DENIED:
        await _ephemeral(interaction, "You are not allowed to use Cursor commands.")
        return None

    if not await _access().can_use_command(interaction.user.id, subcommand):
        await _ephemeral(interaction, "You are not allowed to use that Cursor command.")
        return None

    if not await _policy_allowed(interaction, subcommand):
        await _ephemeral(interaction, "Cursor is not allowed in this channel.")
        return None

    return tier


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

    async def save_model_decision(self, decision: ModelDecision) -> ModelDecision:
        result = await super().save_model_decision(decision)
        self._persist()
        return result


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


async def _download_images(images: list[ImageInput]) -> list[ImageInput]:
    """Download CDN URLs into bounded base64 for approval delay safety."""
    cfg = _cfg()
    client = _client()
    http = await client._ensure_client()
    out: list[ImageInput] = []
    total = 0
    for img in images:
        if img.data_b64:
            size = img.size_bytes or 0
            if total + size > cfg.max_retained_image_bytes:
                break
            out.append(img)
            total += size
            continue
        if not img.url:
            continue
        try:
            resp = await http.get(img.url)
            resp.raise_for_status()
            data = resp.content
            if len(data) > cfg.max_image_bytes:
                continue
            if total + len(data) > cfg.max_retained_image_bytes:
                break
            encoded = encode_image_bytes(data, img.mime_type)
            encoded.source_message_id = img.source_message_id
            encoded.url = img.url
            out.append(encoded)
            total += len(data)
        except Exception:
            # Keep URL as last resort if download fails at request time.
            out.append(img)
    return out


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
) -> None:
    cfg = _cfg()
    scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    client = _client()

    async with sessions.lock_for(scope):
        active = await sessions.get_active(scope)
        if not force_new and agent_id is None and active is not None:
            agent_id = active.agent_id

        if agent_id and not force_new:
            session = await sessions.get_session(scope, agent_id)
            if session and run_is_busy(session.latest_run_status):
                raise BusyRunError()

        status_msg = await _public(interaction, initial_queued_message())
        api_images = [img.to_api() for img in images]

        try:
            if force_new or not agent_id:
                agent, run = await client.create_agent(
                    prompt_text,
                    images=api_images or None,
                    model=model or cfg.default_model or None,
                    repository_url=cfg.default_repository_url,
                    starting_ref=cfg.default_ref,
                    auto_create_pr=cfg.auto_create_pr,
                )
                session = AgentSession(
                    scope=scope,
                    agent_id=agent.id,
                    owner_id=scope.user_id,
                    name=agent.name,
                    model=model or cfg.default_model or agent.model,
                    preferred_model=model or cfg.default_model or None,
                    repository_url=cfg.default_repository_url,
                    starting_ref=cfg.default_ref,
                    latest_run_id=run.id,
                    latest_run_status=run.status,
                    status_channel_id=str(status_msg.channel.id),
                    status_message_id=str(status_msg.id),
                    summary=prompt_text[:200],
                    active=True,
                    last_meaningful_activity_at=utcnow(),
                )
                await sessions.upsert(session)
            else:
                run = await client.create_run(
                    agent_id, prompt_text, images=api_images or None
                )
                session = await sessions.get_session(scope, agent_id)
                if session is None:
                    raise OwnershipError()
                session.latest_run_id = run.id
                session.latest_run_status = run.status
                session.status_channel_id = str(status_msg.channel.id)
                session.status_message_id = str(status_msg.id)
                session.summary = prompt_text[:200]
                session.last_meaningful_activity_at = utcnow()
                await sessions.upsert(session)
        except Exception as exc:
            if grant is not None and getattr(grant, "kind", None) == "once":
                await _access().mark_submit_failed_after_consume(grant)
                await status_msg.edit(
                    content=(
                        "### Error\n"
                        + GrantConsumedError(str(exc)).user_message
                    )[:2000],
                    allowed_mentions=CONTENT_MENTIONS,
                )
                raise GrantConsumedError(str(exc)) from exc
            await status_msg.edit(
                content=f"### Error\n{redact_untrusted(getattr(exc, 'user_message', str(exc)))}"[:2000],
                allowed_mentions=CONTENT_MENTIONS,
            )
            raise

    async def on_activity(_event: str):
        await sessions.touch_activity(scope, session.agent_id)

    sink = DiscordStatusSink(status_msg)
    tracker = RunTracker(
        client,
        sink,
        edit_interval_ms=cfg.status_edit_interval_ms,
        agent_name=session.name or session.agent_id,
        skipped_images=skipped,
        on_meaningful_activity=on_activity,
    )

    async def _runner():
        try:
            snap = await tracker.track(
                session.agent_id,
                session.latest_run_id,
                initial_status=session.latest_run_status,
            )
            session.latest_run_status = snap.status
            session.degraded = snap.degraded
            if snap.status.is_terminal:
                session.last_meaningful_activity_at = utcnow()
            await sessions.upsert(session)
        finally:
            _STATE["trackers"].pop(session.agent_id, None)

    task = asyncio.create_task(_runner())
    _STATE["trackers"][session.agent_id] = task


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
) -> None:
    scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    cfg = _cfg()
    tier = await _access().resolve_tier(interaction.user.id)

    prompt_text, image_inputs, skipped = await _build_context_for_run(
        interaction, prompt, message_ref, images
    )
    await sessions.touch_activity(scope)

    async with sessions.lock_for(scope):
        active = await sessions.get_active(scope)
        preferred = None
        if active is not None:
            preferred = active.preferred_model or cfg.default_model or None
        else:
            preferred = (
                (_STATE.get("user_model_pref") or {}).get(scope.as_str())
                or cfg.default_model
                or None
            )

        # Model mismatch decision (before idle + approval hashing).
        want_new = bool(force_new)
        if (
            not skip_model
            and active is not None
            and not want_new
            and preferred
            and active.model
            and preferred != active.model
            and model_override_choice is None
        ):
            decision = ModelDecision(
                decision_id=new_id("mdl"),
                scope=scope,
                agent_id=active.agent_id,
                preferred_model=preferred,
                agent_model=active.model,
                expires_at=utcnow() + timedelta(minutes=30),
            )
            await sessions.save_model_decision(decision)
            _STATE["pending_run"] = {
                decision.decision_id: {
                    "prompt": prompt,
                    "message_ref": message_ref,
                    "images": images,
                }
            }
            view = ModelDecisionView(decision.decision_id)
            await _ephemeral(
                interaction,
                f"Selected model `{preferred}` differs from this session's "
                f"create-time model `{active.model}`. Follow-up runs cannot change model.",
            )
            # Use followup with view in channel for persistent buttons
            await interaction.followup.send(
                f"Model mismatch for <@{scope.user_id}> — choose how to proceed.",
                view=view,
                ephemeral=True,
            )
            return

        if model_override_choice == ModelChoice.NEW_SESSION:
            want_new = True
        elif model_override_choice == ModelChoice.CONTINUE_ORIGINAL:
            want_new = False
            preferred = active.model if active else preferred

        # Idle decision before approval.
        if (
            not skip_idle
            and not want_new
            and active is not None
            and session_is_idle(active, idle_minutes=cfg.session_idle_prompt_minutes)
        ):
            decision = IdleDecision(
                decision_id=new_id("idle"),
                scope=scope,
                agent_id=active.agent_id,
                expires_at=utcnow() + timedelta(minutes=30),
            )
            await sessions.save_idle_decision(decision)
            _STATE.setdefault("pending_run", {})[decision.decision_id] = {
                "prompt": prompt,
                "message_ref": message_ref,
                "images": images,
                "preferred": preferred,
            }
            view = IdleDecisionView(decision.decision_id)
            if interaction.response.is_done():
                await interaction.followup.send(
                    "This session has been idle. Continue previous, start new, or cancel?",
                    view=view,
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "This session has been idle. Continue previous, start new, or cancel?",
                    view=view,
                    ephemeral=True,
                )
            return

        agent_id = None if want_new else (active.agent_id if active else None)
        envelope = RunRequestEnvelope(
            requester_id=scope.user_id,
            scope=scope,
            prompt_text=prompt_text,
            model=preferred if want_new or active is None else (active.model if active else preferred),
            repository_url=cfg.default_repository_url,
            starting_ref=cfg.default_ref,
            agent_id=agent_id,
            is_follow_up=bool(agent_id),
            image_metas=build_run_prompt(
                prompt_text, direct_images=image_inputs
            ).image_metas(),
        )

        grant = None
        if tier == AccessTier.APPROVAL:
            grant = await _access().find_valid_grant(scope, scope.user_id, envelope)
            if grant is None:
                retained = await _download_images(image_inputs)
                request = await _access().create_approval_request(
                    envelope,
                    prompt_preview=redact_preview(prompt),
                    images=retained,
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
                    f"Images: {len(image_inputs)}\n"
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
                msg = await interaction.channel.send(
                    summary[:2000], view=view, allowed_mentions=approve_mentions
                )
                request.approval_channel_id = str(msg.channel.id)
                request.approval_message_id = str(msg.id)
                await _access().store.save_request(request)
                bot = _STATE.get("bot")
                if bot:
                    bot.add_view(ApprovalView(request.request_id))
                return
            # Consume one-run grants immediately before submit.
            if grant.kind == "once":
                grant = await _access().consume_grant_for_submit(grant, envelope)

        # Defer if needed then launch
        if not interaction.response.is_done():
            await interaction.response.defer()

    await _launch_run(
        interaction,
        prompt_text=prompt_text,
        images=image_inputs,
        skipped=skipped,
        agent_id=agent_id,
        force_new=want_new,
        model=envelope.model,
        grant=grant,
    )


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

    try:
        if kind.startswith("apr_"):
            mode = {"apr_once": "once", "apr_timed": "timed", "apr_deny": "deny"}[kind]
            minutes = _cfg().access.default_grant_minutes if mode == "timed" else None
            request = await _access().decide_request(
                interaction.user.id, token, mode=mode, minutes=minutes
            )
            await interaction.response.send_message(
                f"Decision recorded: `{request.decision.value}`.",
                ephemeral=True,
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
    images = await _access().images.get(request.request_id) or []
    envelope = request.envelope
    # Find grant created by decision
    grant = None
    if request.grant_id:
        grant = await _access().store.get_grant(request.grant_id)
    if grant and grant.kind == "once" and not grant.consumed:
        grant = await _access().consume_grant_for_submit(grant, envelope)

    # Build a synthetic interaction channel send path: post status in original channel.
    channel = interaction.guild.get_channel(int(envelope.scope.channel_id)) if interaction.guild else None
    if channel is None:
        try:
            channel = await interaction.client.fetch_channel(int(envelope.scope.channel_id))
        except Exception:
            channel = interaction.channel

    class _FakeInteraction:
        def __init__(self):
            self.user = type("U", (), {"id": int(envelope.requester_id)})()
            self.guild_id = int(envelope.scope.guild_id)
            self.channel_id = int(envelope.scope.channel_id)
            self.channel = channel
            self.guild = interaction.guild
            self.client = interaction.client
            self.response = _Resp()
            self.followup = channel

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
    # Monkeypatch followup.send
    async def _followup_send(content, **kwargs):
        wait = kwargs.pop("wait", False)
        msg = await channel.send(content, allowed_mentions=kwargs.get("allowed_mentions", CONTENT_MENTIONS))
        fake._msg = msg
        return msg

    fake.followup.send = _followup_send  # type: ignore

    try:
        await _launch_run(
            fake,  # type: ignore
            prompt_text=envelope.prompt_text,
            images=images,
            skipped=[],
            agent_id=envelope.agent_id,
            force_new=not envelope.is_follow_up,
            model=envelope.model,
            grant=grant,
        )
        await _access().images.discard(request.request_id)
        if interaction.message:
            await interaction.message.edit(
                content=f"### Approved\nRequest `{request.request_id}` launched.",
                view=None,
                allowed_mentions=CONTENT_MENTIONS,
            )
    except Exception as exc:
        logger.exception("Approved launch failed")
        await interaction.followup.send(
            f"Approved but launch failed: {getattr(exc, 'user_message', exc)}",
            ephemeral=True,
        )


async def _complete_idle(interaction, decision_id: str, choice: IdleChoice) -> None:
    sessions = _sessions()
    decision = await sessions.get_idle_decision(decision_id)
    if decision is None or decision.consumed:
        raise StaleStateError()
    if decision.expires_at and utcnow() >= decision.expires_at:
        raise StaleStateError(user_message="Idle decision expired.")
    if str(interaction.user.id) != decision.scope.user_id:
        raise AuthorizationError()
    await _gate(interaction, "run")

    async with sessions.lock_for(decision.scope):
        decision = await sessions.get_idle_decision(decision_id)
        if decision is None or decision.consumed:
            raise StaleStateError()
        decision.consumed = True
        decision.choice = choice
        await sessions.save_idle_decision(decision)

    pending = (_STATE.get("pending_run") or {}).pop(decision_id, None)
    await interaction.response.send_message(
        f"Idle choice: `{choice.value}`.", ephemeral=True
    )
    if choice == IdleChoice.CANCEL or not pending:
        return
    await _prepare_and_maybe_launch(
        interaction,
        pending["prompt"],
        pending.get("message_ref"),
        pending.get("images") or [],
        force_new=(choice == IdleChoice.NEW),
        skip_idle=True,
    )


async def _complete_model(interaction, decision_id: str, choice: ModelChoice) -> None:
    sessions = _sessions()
    decision = await sessions.get_model_decision(decision_id)
    if decision is None or decision.consumed:
        raise StaleStateError()
    if str(interaction.user.id) != decision.scope.user_id:
        raise AuthorizationError()

    async with sessions.lock_for(decision.scope):
        decision = await sessions.get_model_decision(decision_id)
        if decision is None or decision.consumed:
            raise StaleStateError()
        decision.consumed = True
        decision.choice = choice
        await sessions.save_model_decision(decision)

    pending = (_STATE.get("pending_run") or {}).pop(decision_id, None)
    await interaction.response.send_message(
        f"Model choice: `{choice.value}`.", ephemeral=True
    )
    if choice == ModelChoice.CANCEL or not pending:
        return
    await _prepare_and_maybe_launch(
        interaction,
        pending["prompt"],
        pending.get("message_ref"),
        pending.get("images") or [],
        skip_model=True,
        model_override_choice=choice,
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
    prompt: Option(str, "Instruction for the agent"),
    message: Option(str, "Message URL or ID for reply-chain context", required=False) = None,
    image1: Option(discord.Attachment, "Image 1", required=False) = None,
    image2: Option(discord.Attachment, "Image 2", required=False) = None,
    image3: Option(discord.Attachment, "Image 3", required=False) = None,
    image4: Option(discord.Attachment, "Image 4", required=False) = None,
    image5: Option(discord.Attachment, "Image 5", required=False) = None,
):
    interaction = ctx.interaction
    if await _gate(interaction, "run") is None:
        return
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


@cursor_group.command(name="stop", description="Cancel your active Cursor run in this channel")
async def cursor_stop(ctx: discord.ApplicationContext):
    interaction = ctx.interaction
    if await _gate(interaction, "stop") is None:
        return
    scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    async with sessions.lock_for(scope):
        active = await sessions.get_active(scope)
        if active is None or not active.latest_run_id:
            await _ephemeral(interaction, "No active run to stop.")
            return
        try:
            await _client().cancel_run(active.agent_id, active.latest_run_id)
            active.latest_run_status = RunStatus.CANCELLED
            await sessions.upsert(active)
            await sessions.touch_activity(scope, active.agent_id)
            await _ephemeral(interaction, f"Cancel requested for `{active.latest_run_id}`.")
        except CursorCloudError as exc:
            await _ephemeral(interaction, exc.user_message)


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
        lines.append(
            f"- `{s.agent_id}` {redact_untrusted(s.name)[:40]} "
            f"[{s.latest_run_status.value}]{mark}"
        )
    await _ephemeral(interaction, "\n".join(lines)[:2000])


@cursor_group.command(name="session", description="Switch your active owned Cursor session")
async def cursor_session(
    ctx: discord.ApplicationContext,
    agent_id: Option(str, "Owned agent id"),
):
    interaction = ctx.interaction
    if await _gate(interaction, "session") is None:
        return
    scope = _scope_from_interaction(interaction)
    try:
        # Validate ownership locally first — never expose org-wide agents.
        session = await _sessions().get_session(scope, agent_id)
        if session is None:
            raise OwnershipError()
        # Optional API check that it still exists.
        try:
            await _client().get_agent(agent_id)
        except CursorCloudError:
            pass
        await _sessions().set_active(scope, agent_id)
        await _sessions().touch_activity(scope, agent_id)
        await _ephemeral(interaction, f"Active session set to `{agent_id}`.")
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)


@cursor_group.command(name="model", description="Show or set preferred model for next new session")
async def cursor_model(
    ctx: discord.ApplicationContext,
    model_id: Option(str, "Model id from /v1/models", required=False) = None,
):
    interaction = ctx.interaction
    if await _gate(interaction, "model") is None:
        return
    scope = _scope_from_interaction(interaction)
    sessions = _sessions()
    if not model_id:
        try:
            models = await _client().list_models()
        except CursorCloudError as exc:
            await _ephemeral(interaction, exc.user_message)
            return
        active = await sessions.get_active(scope)
        preferred = (active.preferred_model if active else None) or _cfg().default_model or "(default)"
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
        active = await sessions.get_active(scope)
        if active is None:
            # Store preference on a placeholder-less ephemeral note via a synthetic session skip:
            await _ephemeral(
                interaction,
                f"Preferred model set to `{model_id}` for your next new session "
                "(no active session yet).",
            )
            # Keep preference in pending map
            _STATE.setdefault("user_model_pref", {})[scope.as_str()] = model_id
            return
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


@cursor_group.command(name="status", description="Show status for your active Cursor run")
async def cursor_status(ctx: discord.ApplicationContext):
    interaction = ctx.interaction
    if await _gate(interaction, "status") is None:
        return
    scope = _scope_from_interaction(interaction)
    active = await _sessions().get_active(scope)
    if active is None or not active.latest_run_id:
        await _ephemeral(interaction, "No active session/run.")
        return
    try:
        run = await _client().get_run(active.agent_id, active.latest_run_id)
        active.latest_run_status = run.status
        await _sessions().upsert(active)
        await _sessions().touch_activity(scope, active.agent_id)
        text = (
            f"### Status\n"
            f"Agent: `{active.agent_id}`\n"
            f"Run: `{run.id}`\n"
            f"State: `{run.status.value}`\n"
        )
        if run.result:
            text += f"\n{redact_untrusted(run.result)[:1500]}"
        # Try edit existing status message
        if active.status_channel_id and active.status_message_id:
            try:
                channel = interaction.guild.get_channel(int(active.status_channel_id)) if interaction.guild else interaction.channel
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
    user: Option(discord.User, "Target user"),
    tier: Option(str, "1, 2, 3, or reset"),
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
    grant_id: Option(str, "Grant id"),
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
    request_id: Option(str, "Approval request id"),
    mode: Option(str, "once or timed", choices=["once", "timed"]),
    minutes: Option(int, "Timed grant minutes", required=False) = None,
):
    interaction = ctx.interaction
    if await _gate(interaction, "approve") is None:
        return
    try:
        # Approvers may be Tier0/1 even if can_use_command blocks tier2 approve name —
        # re-check approver explicitly.
        await _access().require_approver(interaction.user.id)
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
    request_id: Option(str, "Approval request id"),
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


def _register_commands(bot: discord.Bot) -> None:
    # Avoid duplicate registration across reconnects / repeated ready.
    pending = list(getattr(bot, "pending_application_commands", []) or [])
    attached = list(getattr(bot, "application_commands", []) or [])
    for cmd in pending + attached:
        if getattr(cmd, "name", None) == "cursor":
            return
    bot.add_application_command(cursor_group)


async def _register_views(bot: discord.Bot) -> None:
    access = _STATE.get("access")
    sessions = _STATE.get("sessions")
    if access:
        for request in await access.store.list_requests():
            if request.decision.value == "pending":
                bot.add_view(ApprovalView(request.request_id))
    if sessions:
        state = sessions.export_state()
        for decision_id in state.get("idle") or {}:
            bot.add_view(IdleDecisionView(decision_id))
        for decision_id in state.get("model") or {}:
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
                    session.degraded = True
                    await sessions.upsert(session)
                    continue

                sink = DiscordStatusSink(msg)
                tracker = RunTracker(
                    client,
                    sink,
                    edit_interval_ms=_cfg().status_edit_interval_ms,
                    agent_name=session.name or session.agent_id,
                )

                async def _resume(sess=session, tr=tracker):
                    snap = await tr.track(
                        sess.agent_id,
                        sess.latest_run_id,
                        initial_status=sess.latest_run_status,
                    )
                    sess.latest_run_status = snap.status
                    await sessions.upsert(sess)

                _STATE["trackers"][session.agent_id] = asyncio.create_task(_resume())
        except Exception:
            logger.exception("Cursor reconcile failed for %s", session.agent_id)


async def _expiry_loop() -> None:
    while True:
        try:
            if _STATE.get("access"):
                await _access().expire_stale_requests()
        except Exception:
            logger.exception("Cursor approval expiry loop failed")
        await asyncio.sleep(60)


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
    else:
        sessions = MemorySessionStore(max_recent=cfg.max_recent_sessions)
        access_store = MemoryAccessStore(audit_limit=cfg.access.audit_history_limit)

    _STATE["sessions"] = sessions
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

    await _register_views(bot)

    if cfg.is_ready and not _STATE.get("reconcile_started"):
        _STATE["reconcile_started"] = True
        asyncio.create_task(_reconcile_runs())
        asyncio.create_task(_expiry_loop())


async def cursor_bot_hook(sonata: AI_Manager, bot: discord.Bot) -> None:
    """Invoked from SonataClient.on_ready for runtime/Beacon setup."""
    await setup_cursor_runtime(sonata, bot)


@MANAGER.mem(
    {},
    key="cursor",
    hook=cursor_bot_hook,
)
def init_cursor(_M):
    return None
