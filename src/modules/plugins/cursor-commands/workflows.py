"""Run orchestration for the Cursor Discord adapter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import discord
from discord.ext import commands as ext_commands

from cursor_cloud.access import new_id, redact_preview
from cursor_cloud.context import (
    build_run_prompt,
    collect_chain_attachments,
    encode_image_bytes,
    images_from_discord_attachments,
    metas_from_images,
    metas_match,
    parse_message_reference,
)
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
    DecisionKind,
    GitBranchInfo,
    IdleChoice,
    ImageInput,
    ModelChoice,
    PendingDecision,
    PromptImageMeta,
    RunRequestEnvelope,
    RunStatus,
    ScopeKey,
    utcnow,
)
from cursor_cloud.run_tracker import RunTracker
from cursor_cloud.session_store import run_is_busy, session_is_idle
from cursor_cloud.status_renderer import initial_queued_message, redact_untrusted
from cursor_cloud.thread_session import (
    owner_reply_to_human,
    policy_channel_id as resolve_policy_channel_id,
    thread_session_immutable_violation,
)
from cursor_cloud.thread_renderer import THREAD_THINKING_INDICATOR
from cursor_cloud.thread_sink import ThreadActivitySink
from cursor_cloud.run_log import sanitize_log_summary
from modules.utils import get_reference_chain, get_reference_message_chain

from .discord_ui import (
    CONTENT_MENTIONS,
    ApprovalView,
    ChannelUI,
    DiscordStatusSink,
    IdleDecisionView,
    InteractionUI,
    LaunchUI,
    ModelDecisionView,
    as_launch_ui,
    _channel_is_thread,
    _create_public_agent_thread,
    _defer,
    _ephemeral,
    _generate_session_title,
    _gate,
    _interaction_shim_for_channel,
    _interaction_shim_from_message,
    _maybe_rename_thread,
    _maybe_unarchive_thread,
    _policy_allowed,
    _policy_channel_id_from_interaction,
    _public,
    _resolve_discord_channel,
    _revalidate_run_auth,
    _role_ids,
    _role_ids_for_user,
    _sanitize_thread_title,
    _scope_from_interaction,
    _scope_from_message,
    _title_from_prompt,
    _translate_thread_final_for_sona,
)
from .runtime import (
    CursorRuntime,
    _discard_retention_key,
    get_runtime,
)

logger = logging.getLogger("sonata.cursor")

@dataclass
class RunContext:
    """Who/where/policy for a run — built once per entrypoint."""

    scope: ScopeKey
    role_ids: list[str]
    thread_bound: bool
    parent_channel_id: str | None
    policy_channel_id: str
    status_msg: Any | None
    subcommand: str
    skip_status_post: bool = False
    agent_display_name: str | None = None
    user_prompt: str | None = None
    user_name: str | None = None

    @classmethod
    async def build(
        cls,
        *,
        sessions,
        scope: ScopeKey,
        role_ids: list[str],
        force_new: bool | None = None,
        thread_bound: bool = False,
        parent_channel_id: str | None = None,
        policy_channel_id: str | None = None,
        status_msg: Any | None = None,
        skip_status_post: bool = False,
        auth_subcommand: str | None = None,
        channel: Any | None = None,
        agent_display_name: str | None = None,
        user_prompt: str | None = None,
        user_name: str | None = None,
    ) -> RunContext:
        """Inherit thread binding / parent policy from an active session or channel."""
        active = await sessions.get_active(scope)
        if active is not None and active.thread_bound:
            thread_bound = True
            parent_channel_id = parent_channel_id or active.parent_channel_id
            if status_msg is None and active.status_message_id and channel is not None:
                try:
                    status_msg = await channel.fetch_message(int(active.status_message_id))
                    skip_status_post = True
                except Exception:
                    status_msg = None

        if policy_channel_id is None and parent_channel_id is None and channel is not None:
            parent_id = getattr(channel, "parent_id", None)
            # Duck-typed thread: has parent_id or Discord Thread type name.
            is_thread = bool(parent_id) or type(channel).__name__ == "Thread"
            if is_thread and parent_id:
                parent_channel_id = str(parent_id)

        pol_ch = resolve_policy_channel_id(
            channel_id=scope.channel_id,
            session=active,
            parent_channel_id=policy_channel_id or parent_channel_id,
        )
        want_new = bool(force_new)
        subcommand = auth_subcommand or ("new" if thread_bound and want_new else "run")
        return cls(
            scope=scope,
            role_ids=list(role_ids or []),
            thread_bound=bool(thread_bound),
            parent_channel_id=parent_channel_id,
            policy_channel_id=pol_ch,
            status_msg=status_msg,
            subcommand=subcommand,
            skip_status_post=bool(skip_status_post),
            agent_display_name=agent_display_name,
            user_prompt=user_prompt,
            user_name=user_name,
        )

@dataclass
class PreparedRun:
    """What to submit — output of ``prepare`` when ready to launch."""

    ctx: RunContext
    prompt_text: str
    images: list[ImageInput]
    skipped: list[str]
    envelope: RunRequestEnvelope
    force_new: bool
    agent_id: str | None
    grant: Any | None = None  # RunGrant | None

    def to_pending_dict(self) -> dict[str, Any]:
        """Serializable subset for idle/model decision re-entry."""
        return {
            "prompt_text": self.prompt_text,
            "skipped": list(self.skipped),
            "force_new": self.force_new,
            "agent_id": self.agent_id,
            "thread_bound": self.ctx.thread_bound,
            "parent_channel_id": self.ctx.parent_channel_id,
            "policy_channel_id": self.ctx.policy_channel_id,
            "subcommand": self.ctx.subcommand,
            "envelope_model": self.envelope.model,
        }

@dataclass(frozen=True)
class ApprovalPending:
    request_id: str | None = None

@dataclass(frozen=True)
class DecisionPending:
    kind: str  # "idle" | "model"
    decision_id: str | None = None

def _idle_still_applies(rt: CursorRuntime, active: AgentSession | None, preferred: str | None) -> bool:
    if active is None:
        return False
    return session_is_idle(
        active, idle_minutes=rt.config.session_idle_prompt_minutes
    )

def _model_still_applies(
    rt: CursorRuntime, active: AgentSession | None, preferred: str | None
) -> bool:
    return bool(
        active is not None
        and preferred
        and active.model
        and preferred != active.model
    )

def _idle_reentry_kwargs(choice: str) -> dict[str, Any]:
    return {
        "skip_idle": True,
        "force_new": choice == IdleChoice.NEW.value,
    }

def _model_reentry_kwargs(choice: str) -> dict[str, Any]:
    return {
        "skip_model": True,
        "model_override_choice": ModelChoice(choice),
    }

_DECISION_KINDS: dict[str, dict[str, Any]] = {
    "idle": {
        "choice_map": {
            "idle_cont": IdleChoice.CONTINUE.value,
            "idle_new": IdleChoice.NEW.value,
            "idle_cancel": IdleChoice.CANCEL.value,
        },
        "view_factory": IdleDecisionView,
        "still_applies": _idle_still_applies,
        "reentry_kwargs": _idle_reentry_kwargs,
        "cancel_choice": IdleChoice.CANCEL.value,
        "id_prefix": "idle",
        "new_session_choice": IdleChoice.NEW.value,
        "already_pending": "An idle session choice is already pending",
        "notify": "Session idle — choose how to proceed in the channel message.",
        "edit_label": "Idle",
        "expired_label": "Idle session",
        "ack_label": "Idle choice",
        "channel_content": lambda scope, active, preferred: (
            f"### Idle session\n"
            f"<@{scope.user_id}> — session `{active.agent_id}` has been idle. "
            f"Continue previous, start new, or cancel?"
        ),
        "extras": lambda active, preferred: {},
    },
    "model": {
        "choice_map": {
            "mdl_new": ModelChoice.NEW_SESSION.value,
            "mdl_cont": ModelChoice.CONTINUE_ORIGINAL.value,
            "mdl_cancel": ModelChoice.CANCEL.value,
        },
        "view_factory": ModelDecisionView,
        "still_applies": _model_still_applies,
        "reentry_kwargs": _model_reentry_kwargs,
        "cancel_choice": ModelChoice.CANCEL.value,
        "id_prefix": "mdl",
        "new_session_choice": ModelChoice.NEW_SESSION.value,
        "already_pending": "A model choice is already pending",
        "notify": "Model mismatch — choose how to proceed in the channel message.",
        "edit_label": "Model",
        "expired_label": "Model choice",
        "ack_label": "Model choice",
        "channel_content": lambda scope, active, preferred: (
            f"### Model choice\n"
            f"<@{scope.user_id}> selected `{preferred}` but session "
            f"`{active.agent_id}` was created with `{active.model}`.\n"
            f"Follow-up runs cannot change model."
        ),
        "extras": lambda active, preferred: {
            "preferred_model": preferred or "",
            "agent_model": active.model or "",
        },
    },
}

def _decision_kind_for_component(kind: str) -> tuple[str, str] | None:
    """Map a custom-id action (idle_cont / mdl_new / …) to (kind, choice)."""
    for dkind, spec in _DECISION_KINDS.items():
        choice_map = spec["choice_map"]
        if kind in choice_map:
            return dkind, choice_map[kind]
    return None

async def _download_images(images: list[ImageInput]) -> list[ImageInput]:
    """Download Discord CDN URLs via unauthenticated allowlisted client.

    Never reuse the Cursor API Basic-auth client. Fail closed on host/redirect
    violations rather than falling back to raw CDN URLs for pending approvals.
    """
    rt = get_runtime()
    cfg = rt.config
    downloader = rt.ensure_cdn()
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
    prepared_meta: dict[str, Any] | None = None,
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
    if prepared_meta is not None:
        data["prepared_meta"] = dict(prepared_meta)
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
    images = await get_runtime().access.images.get(str(key)) or []
    if expected and (not images or not metas_match(expected, metas_from_images(images))):
        raise ValidationError(
            "Pending image metadata mismatch or process-local retention lost",
            user_message=restart_msg,
        )
    if not expected and not images:
        return []
    return images

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
    cfg = get_runtime().config
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
    cfg = get_runtime().config
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

async def handle_thread_message(message: discord.Message) -> bool:
    """Owner plain messages in bound threads become agent follow-ups."""
    if message.author.bot:
        return False
    if not _channel_is_thread(message.channel):
        return False
    if not message.content and not message.attachments:
        return False

    rt = get_runtime()
    sessions = rt.sessions
    session = await sessions.find_thread_session(str(message.channel.id))
    if session is None:
        return False

    msg_key = str(message.id)
    if rt.note_handled_thread_message(msg_key):
        return True

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
    # auth / build context / hit the Cursor API. Reuse a visible Activity
    # message when present; after a cleared terminal stub, post a fresh one.
    activity_msg = None
    if session.status_channel_id and session.status_message_id:
        try:
            activity_msg = await message.channel.fetch_message(
                int(session.status_message_id)
            )
        except Exception:
            activity_msg = None
    if activity_msg is not None:
        prior = (activity_msg.content or "").strip()
        if prior in {"", "\u200b"}:
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
            rt,
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

    ui = ChannelUI.from_message(message, client=rt.bot)

    try:
        prompt_text, image_inputs, skipped = await _build_context_from_message(
            message, prompt or "(see attachments)"
        )
    except Exception:
        logger.exception("Cursor thread follow-up context failed")
        return True

    try:
        outcome = await prepare(
            rt,
            ui,
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
        if isinstance(outcome, PreparedRun):
            await launch(rt, ui, outcome)
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

def finalize_session_from_snapshot(session, snap, *, sink=None) -> None:
    """Apply tracker snapshot fields onto a session (launch + reconcile postlude)."""
    session.latest_run_status = snap.status
    if sink is not None:
        session.degraded = snap.degraded or getattr(sink, "degraded", False)
    else:
        session.degraded = snap.degraded or session.degraded
    if snap.status.is_terminal:
        session.last_meaningful_activity_at = utcnow()
        branches = list(getattr(snap, "git_branches", None) or [])
        if branches:
            session.latest_git = list(branches)

def _auth_interaction_from_ui(ui: LaunchUI) -> discord.Interaction | None:
    if isinstance(ui, InteractionUI) and isinstance(ui.interaction, discord.Interaction):
        return ui.interaction
    return None

def _ui_source(ui: LaunchUI):
    """Duck-typed Interaction / ChannelUI for scope and context builders."""
    return ui.interaction if isinstance(ui, InteractionUI) else ui

async def launch(rt: CursorRuntime, ui: LaunchUI, prepared: PreparedRun) -> AgentSession:
    """Submit a prepared run: busy pre-check → status → auth+consume under lock."""
    cfg = rt.config
    ctx = prepared.ctx
    scope = ctx.scope
    sessions = rt.sessions
    client = rt.client
    role_ids = list(ctx.role_ids or [])
    thread_bound = ctx.thread_bound
    parent_channel_id = ctx.parent_channel_id
    pol_ch = ctx.policy_channel_id
    auth_subcommand = ctx.subcommand
    force_new = prepared.force_new
    agent_id = prepared.agent_id
    prompt_text = prepared.prompt_text
    images = prepared.images
    skipped = prepared.skipped
    envelope = prepared.envelope
    grant = prepared.grant
    model = envelope.model
    status_msg = ctx.status_msg
    skip_status_post = ctx.skip_status_post
    agent_display_name = ctx.agent_display_name
    user_prompt = ctx.user_prompt
    user_name = ctx.user_name
    auth_interaction = _auth_interaction_from_ui(ui)

    # Pre-check busy under the scope lock BEFORE posting public Queued status,
    # so concurrent callers cannot leave orphan status messages.
    async with sessions.lock_for(scope):
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
        status_msg = await ui.post_status(initial_queued_message())

    status_cleanup: tuple[str, str] | None = None  # (kind, message)
    grant_consumed = False
    session: AgentSession | None = None
    pending_exc: BaseException | None = None

    try:
        async with sessions.lock_for(scope):
            # Sole launch auth: under the submit lock immediately before grant consume.
            await _revalidate_run_auth(
                rt,
                user_id=scope.user_id,
                guild_id=scope.guild_id,
                channel_id=scope.channel_id,
                role_ids=role_ids,
                subcommand=auth_subcommand,
                interaction=auth_interaction,
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
                grant = await rt.access.consume_grant_for_submit(grant, envelope)
                grant_consumed = True

            # Defensive: if busy somehow appears after consume, fail-closed.
            if agent_id and not force_new:
                existing = await sessions.get_session(scope, agent_id)
                if existing and run_is_busy(existing.latest_run_status):
                    if grant_consumed and grant is not None:
                        await rt.access.mark_submit_failed_after_consume(grant)
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
                    logger.warning(
                        "cursor.launch_create_agent scope=%s force_new=%s model=%s",
                        scope,
                        force_new,
                        model or cfg.default_model,
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
                    if not agent.id or not run.id:
                        raise ValidationError(
                            "create_agent missing agent/run id",
                            user_message=(
                                "Cursor did not return a usable agent/run id. "
                                "Try again in a moment."
                            ),
                            code="missing_run_id",
                        )
                    logger.warning(
                        "cursor.launch_agent_created agent=%s run=%s status=%s",
                        agent.id,
                        run.id,
                        getattr(run.status, "value", run.status),
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
                    existing_tracker = rt.trackers.get(agent_id)
                    prior_session = await sessions.get_session(scope, agent_id)
                    prior_status = None
                    if prior_session is not None:
                        prior_status = getattr(
                            prior_session.latest_run_status,
                            "value",
                            prior_session.latest_run_status,
                        )
                    logger.warning(
                        "cursor.launch_create_run agent=%s prior_status=%s "
                        "tracker_alive=%s",
                        agent_id,
                        prior_status,
                        bool(existing_tracker and not existing_tracker.done()),
                    )
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
                    logger.warning(
                        "cursor.launch_run_created agent=%s run=%s status=%s",
                        agent_id,
                        run.id,
                        getattr(run.status, "value", run.status),
                    )
            except BusyRunError:
                if grant_consumed and grant is not None:
                    await rt.access.mark_submit_failed_after_consume(grant)
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
                    await rt.access.mark_submit_failed_after_consume(grant)
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

        run_logs = rt.ensure_run_logs()
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
            channel = status_msg.channel if status_msg else ui.channel
            latest_user_prompt = (user_prompt or "").strip()
            latest_user_name = (user_name or "").strip() or "User"

            async def _thread_final_translator(
                final: str,
                *,
                _prompt=latest_user_prompt,
                _name=latest_user_name,
            ) -> str:
                return await _translate_thread_final_for_sona(
                    final,
                    user_prompt=_prompt,
                    user_name=_name,
                )

            sink = ThreadActivitySink(
                channel,
                status_msg,
                edit_interval_ms=cfg.status_edit_interval_ms,
                allowed_mentions=CONTENT_MENTIONS,
                final_translator=_thread_final_translator,
                include_chat_info=bool(force_new),
                chat_info_model=session.model,
                chat_info_repository_url=session.repository_url,
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
                logger.warning(
                    "cursor.tracker_task_start agent=%s run=%s status=%s",
                    session.agent_id,
                    session.latest_run_id,
                    getattr(session.latest_run_status, "value", session.latest_run_status),
                )
                snap = await tracker.track(
                    session.agent_id,
                    session.latest_run_id,
                    initial_status=session.latest_run_status,
                )
                finalize_session_from_snapshot(session, snap, sink=sink)
                await sessions.upsert(session)
                logger.warning(
                    "cursor.tracker_task_end agent=%s run=%s status=%s err=%r",
                    session.agent_id,
                    session.latest_run_id,
                    getattr(snap.status, "value", snap.status),
                    (snap.error_message or "")[:200],
                )
            finally:
                rt.trackers.pop(session.agent_id, None)

        prior = rt.trackers.get(session.agent_id)
        if prior is not None and not prior.done():
            logger.warning(
                "cursor.tracker_overwrite agent=%s run=%s prior_alive=True",
                session.agent_id,
                session.latest_run_id,
            )
        rt.trackers[session.agent_id] = asyncio.create_task(_runner())
    return session

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
    user_prompt: str | None = None,
    user_name: str | None = None,
) -> AgentSession:
    """Compat wrapper — builds PreparedRun and calls ``launch``."""
    rt = get_runtime()
    ui = as_launch_ui(interaction, client=rt.bot)
    scope = scope or _scope_from_interaction(_ui_source(ui))
    user = getattr(_ui_source(ui), "user", None)
    if role_ids is None:
        role_ids = _role_ids(user) if user is not None else []
    ctx = await RunContext.build(
        sessions=rt.sessions,
        scope=scope,
        role_ids=role_ids,
        force_new=force_new,
        thread_bound=thread_bound,
        parent_channel_id=parent_channel_id,
        policy_channel_id=policy_channel_id,
        status_msg=status_msg,
        skip_status_post=skip_status_post,
        channel=ui.channel,
        agent_display_name=agent_display_name,
        user_prompt=user_prompt,
        user_name=user_name,
    )
    if envelope is None:
        envelope = RunRequestEnvelope(
            requester_id=scope.user_id,
            scope=scope,
            prompt_text=prompt_text,
            model=model,
            repository_url=rt.config.default_repository_url,
            starting_ref=rt.config.default_ref,
            agent_id=agent_id,
            is_follow_up=bool(agent_id) and not force_new,
            image_metas=metas_from_images(images),
        )
    prepared = PreparedRun(
        ctx=ctx,
        prompt_text=prompt_text,
        images=images,
        skipped=skipped,
        envelope=envelope,
        force_new=force_new,
        agent_id=agent_id,
        grant=grant,
    )
    return await launch(rt, ui, prepared)

async def _rollback_decision(
    *,
    decision_id: str,
    scope: ScopeKey,
    retention_key: str | None,
    cancel_choice: str,
) -> None:
    sessions = get_runtime().sessions
    async with sessions.lock_for(scope):
        decision = await sessions.get_decision(decision_id)
        if decision is not None:
            decision.consumed = True
            decision.choice = cancel_choice
            await sessions.save_decision(decision)
        await sessions.pop_pending_payload(decision_id)
    await _discard_retention_key(retention_key)

async def offer_decision(
    rt: CursorRuntime,
    ui: LaunchUI,
    kind: DecisionKind,
    *,
    scope: ScopeKey,
    active: AgentSession,
    preferred: str | None,
    prompt: str,
    prompt_text: str,
    message_ref: str | None,
    image_inputs: list[ImageInput],
    skipped: list[str],
    prepared_meta: dict[str, Any] | None = None,
) -> bool:
    """Reserve+post an idle/model decision. Returns True if posted/deduped."""
    spec = _DECISION_KINDS[kind]
    sessions = rt.sessions
    retained = await _download_images(image_inputs) if image_inputs else []
    retention_key = new_id("ret") if retained else None
    decision = PendingDecision(
        decision_id=new_id(spec["id_prefix"]),
        scope=scope,
        agent_id=active.agent_id,
        kind=kind,
        expires_at=utcnow() + timedelta(minutes=30),
        extras=spec["extras"](active, preferred),
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
        prepared_meta=prepared_meta,
    )

    async with sessions.lock_for(scope):
        active_now = await sessions.get_active(scope)
        if not spec["still_applies"](rt, active_now, preferred):
            return False
        existing = await sessions.find_open_decision(scope, kind)
        if existing is not None:
            await ui.notify(
                f"{spec['already_pending']} (`{existing.decision_id}`).",
            )
            return True
        if retention_key and retained:
            await rt.access.images.put(
                retention_key, retained, expires_at=decision.expires_at
            )
        await sessions.save_pending_payload(decision.decision_id, payload)
        reserved = await sessions.reserve_decision(decision)
        if reserved is None:
            await _discard_retention_key(retention_key)
            await sessions.pop_pending_payload(decision.decision_id)
            existing = await sessions.find_open_decision(scope, kind)
            await ui.notify(
                f"{spec['already_pending']} (`{getattr(existing, 'decision_id', '?')}`).",
            )
            return True

    view = spec["view_factory"](decision.decision_id)
    try:
        msg = await ui.channel.send(
            spec["channel_content"](scope, active, preferred),
            view=view,
            allowed_mentions=discord.AllowedMentions(
                users=True, everyone=False, roles=False
            ),
        )
    except Exception:
        await _rollback_decision(
            decision_id=decision.decision_id,
            scope=scope,
            retention_key=retention_key,
            cancel_choice=spec["cancel_choice"],
        )
        raise

    decision.message_channel_id = str(msg.channel.id)
    decision.message_id = str(msg.id)
    await sessions.save_decision(decision)
    bot = rt.bot
    if bot:
        bot.add_view(spec["view_factory"](decision.decision_id))
    await ui.notify(spec["notify"])
    return True

async def prepare(
    rt: CursorRuntime,
    ui: LaunchUI,
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
) -> PreparedRun | ApprovalPending | DecisionPending:
    """Prepare auth/context; return PreparedRun or a pending outcome (does not launch)."""
    sessions = rt.sessions
    cfg = rt.config
    src = _ui_source(ui)
    scope = scope_override or _scope_from_interaction(src)
    role_ids = _role_ids(ui.user)

    ctx = await RunContext.build(
        sessions=sessions,
        scope=scope,
        role_ids=role_ids,
        force_new=force_new,
        thread_bound=thread_bound,
        parent_channel_id=parent_channel_id,
        policy_channel_id=policy_channel_id,
        status_msg=status_msg,
        skip_status_post=skip_status_post,
        auth_subcommand=auth_subcommand,
        channel=ui.channel,
        agent_display_name=agent_display_name,
        user_prompt=prompt,
        user_name=(
            getattr(ui.user, "display_name", None)
            or getattr(ui.user, "name", None)
            or "User"
        ),
    )
    thread_bound = ctx.thread_bound
    parent_channel_id = ctx.parent_channel_id
    pol_ch = ctx.policy_channel_id
    status_msg = ctx.status_msg
    skip_status_post = ctx.skip_status_post
    subcommand = ctx.subcommand

    # Gate DENIED / Tier3 and policy before any work (once at prepare entry).
    tier = await _revalidate_run_auth(
        rt,
        user_id=scope.user_id,
        guild_id=scope.guild_id,
        channel_id=scope.channel_id,
        role_ids=role_ids,
        subcommand=subcommand,
        interaction=_auth_interaction_from_ui(ui),
        policy_channel_id=pol_ch,
    )

    if prebuilt is None:
        prompt_text, image_inputs, skipped = await _build_context_for_run(
            src, prompt, message_ref, images
        )
    else:
        prompt_text, image_inputs, skipped = prebuilt

    # Idle/model decisions MUST run before refreshing meaningful activity.
    active = await sessions.get_active(scope)
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

    def _pending_meta(*, force: bool, agent: str | None) -> dict[str, Any]:
        return {
            "prompt_text": prompt_text,
            "skipped": list(skipped),
            "force_new": force,
            "agent_id": agent,
            "thread_bound": thread_bound,
            "parent_channel_id": parent_channel_id,
            "policy_channel_id": pol_ch,
            "subcommand": subcommand,
            "envelope_model": preferred,
        }

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
        posted = await offer_decision(
            rt,
            ui,
            "model",
            scope=scope,
            active=active,
            preferred=preferred,
            prompt=prompt,
            prompt_text=prompt_text,
            message_ref=message_ref,
            image_inputs=image_inputs,
            skipped=skipped,
            prepared_meta=_pending_meta(force=False, agent=active.agent_id),
        )
        if posted:
            return DecisionPending(kind="model")
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
        posted = await offer_decision(
            rt,
            ui,
            "idle",
            scope=scope,
            active=active,
            preferred=preferred,
            prompt=prompt,
            prompt_text=prompt_text,
            message_ref=message_ref,
            image_inputs=image_inputs,
            skipped=skipped,
            prepared_meta=_pending_meta(
                force=False, agent=active.agent_id if active else None
            ),
        )
        if posted:
            return DecisionPending(kind="idle")
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
        grant = await rt.access.find_valid_grant(scope, scope.user_id, envelope)
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
            request = await rt.access.create_approval_request(
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
            approvers = await rt.access.current_approver_ids()
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
            # Thread-bound approvals are posted publicly (with buttons); skip the
            # extra "waiting for approval" ack — it's redundant with the card.
            if not thread_bound:
                await ui.notify(
                    f"Approval pending (`{request.request_id}`). Approvers have been notified.",
                )
            # Post approval in the parent channel for thread-bound new sessions
            # so approvers see it outside the private-feeling agent thread.
            approve_channel = ui.channel
            if thread_bound and parent_channel_id:
                bot = rt.bot
                try:
                    parent = None
                    if bot is not None:
                        parent = bot.get_channel(int(parent_channel_id))
                        if parent is None:
                            parent = await bot.fetch_channel(int(parent_channel_id))
                    if parent is not None:
                        approve_channel = parent
                except Exception:
                    approve_channel = ui.channel
            msg = await approve_channel.send(
                summary[:2000], view=view, allowed_mentions=approve_mentions
            )
            request.approval_channel_id = str(msg.channel.id)
            request.approval_message_id = str(msg.id)
            await rt.access.store.save_request(request)
            bot = rt.bot
            if bot:
                bot.add_view(ApprovalView(request.request_id))
            return ApprovalPending(request_id=request.request_id)

    await ui.ack()

    # Verify retained images still match envelope before submit.
    if not metas_match(envelope.image_metas, metas_from_images(submit_images)):
        raise ValidationError(
            "Image metadata mismatch before submit",
            user_message="Image set no longer matches the approved request; please resubmit.",
        )

    # Refresh ctx fields that may have changed during prepare.
    ctx = RunContext(
        scope=scope,
        role_ids=role_ids,
        thread_bound=thread_bound,
        parent_channel_id=parent_channel_id,
        policy_channel_id=pol_ch,
        status_msg=status_msg,
        subcommand=subcommand,
        skip_status_post=skip_status_post or (thread_bound and status_msg is not None),
        agent_display_name=agent_display_name or ctx.agent_display_name,
        user_prompt=prompt,
        user_name=ctx.user_name,
    )
    return PreparedRun(
        ctx=ctx,
        prompt_text=prompt_text,
        images=submit_images,
        skipped=skipped,
        envelope=envelope,
        force_new=want_new,
        agent_id=agent_id,
        grant=grant,
    )

async def _prepare_and_maybe_launch(
    interaction: discord.Interaction,
    prompt: str,
    message_ref: str | None,
    images: list[discord.Attachment | None],
    **kwargs,
) -> str:
    """Compat wrapper — prepare then launch; returns legacy outcome strings."""
    rt = get_runtime()
    ui = as_launch_ui(interaction, client=rt.bot)
    outcome = await prepare(rt, ui, prompt, message_ref, images, **kwargs)
    if isinstance(outcome, ApprovalPending):
        return "approval_pending"
    if isinstance(outcome, DecisionPending):
        return "decision_pending"
    await launch(rt, ui, outcome)
    return "launched"

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
            minutes = get_runtime().config.access.default_grant_minutes if mode == "timed" else None
            # Before approving: fail closed if requester was demoted / policy revoked.
            if mode in {"once", "timed"}:
                pending_req = await get_runtime().access.store.get_request(token)
                if pending_req is not None and pending_req.envelope is not None:
                    env = pending_req.envelope
                    try:
                        await _revalidate_run_auth(
                            get_runtime(),
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
                        await get_runtime().access.deny_unauthorized_request(
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
            request = await get_runtime().access.decide_request(
                interaction.user.id, token, mode=mode, minutes=minutes
            )
            await _ephemeral(
                interaction,
                f"Decision recorded: `{request.decision.value}`.",
            )
            if request.decision.value.startswith("approved"):
                # Auto-launch for the requester using retained images.
                # Launch failures must not surface as "Could not process that control"
                # — decision already stuck; report launch errors explicitly.
                try:
                    await _launch_approved_request(interaction, request)
                except Exception:
                    logger.exception("Cursor approved launch crashed after decision")
                    await _ephemeral(
                        interaction,
                        "Approved but launch failed unexpectedly. "
                        "Ask the requester to retry `/cursor run` or `$agent`.",
                    )
            elif interaction.message:
                try:
                    await interaction.message.edit(
                        content=f"### Approval {request.decision.value}\nRequest `{request.request_id}`",
                        view=None,
                        allowed_mentions=CONTENT_MENTIONS,
                    )
                except discord.HTTPException:
                    pass
            return True

        resolved = _decision_kind_for_component(kind)
        if resolved is not None:
            _dkind, choice = resolved
            await complete_decision(
                get_runtime(),
                InteractionUI(interaction),
                token,
                choice,
            )
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
    access = get_runtime().access
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
            get_runtime(),
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

    try:
        grant = None
        if request.grant_id:
            grant = await access.store.get_grant(request.grant_id)
            if grant is not None and (
                grant.revoked or (grant.kind == "once" and grant.consumed)
            ):
                await _ephemeral(interaction, "Request already used or expired.")
                return

        channel = await _resolve_discord_channel(
            interaction.guild,
            interaction.client,
            envelope.scope.channel_id,
        )
        if channel is None:
            channel = interaction.channel
        if channel is None:
            await _ephemeral(
                interaction,
                "Approved but could not resolve the target channel to launch.",
            )
            return

        ui = ChannelUI.for_channel(
            channel,
            user_id=envelope.requester_id,
            guild_id=envelope.scope.guild_id,
            guild=interaction.guild,
            client=interaction.client,
        )

        sessions = get_runtime().sessions
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
        status_channel_id = request.status_channel_id or (
            active.status_channel_id if active else None
        )
        if thread_bound and status_message_id:
            status_channel = channel
            if status_channel_id and str(status_channel_id) != str(channel.id):
                status_channel = await _resolve_discord_channel(
                    interaction.guild,
                    interaction.client,
                    status_channel_id,
                ) or channel
            try:
                status_msg = await status_channel.fetch_message(int(status_message_id))
            except Exception:
                status_msg = None

        approved_title = None
        if thread_bound and status_msg is not None:
            approved_title = getattr(status_msg.channel, "name", None)
        force_new = not envelope.is_follow_up
        subcommand = "new" if thread_bound and force_new else "run"
        ctx = RunContext(
            scope=scope,
            role_ids=role_ids,
            thread_bound=thread_bound,
            parent_channel_id=parent_channel_id,
            policy_channel_id=pol_ch,
            status_msg=status_msg,
            subcommand=subcommand,
            skip_status_post=thread_bound and status_msg is not None,
            agent_display_name=approved_title,
            user_prompt=request.prompt_preview or envelope.prompt_text,
            user_name="User",
        )
        prepared = PreparedRun(
            ctx=ctx,
            prompt_text=envelope.prompt_text,
            images=images,
            skipped=[],
            envelope=envelope,
            force_new=force_new,
            agent_id=envelope.agent_id,
            grant=grant,
        )
        await launch(get_runtime(), ui, prepared)
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
        detail = getattr(exc, "user_message", None) or str(exc)
        await _ephemeral(
            interaction,
            f"Approved but launch failed: {detail}"[:2000],
        )

async def complete_decision(
    rt: CursorRuntime,
    ui: LaunchUI,
    decision_id: str,
    choice: str,
) -> None:
    """Consume an idle/model decision and resume the stored PreparedRun with one override."""
    sessions = rt.sessions
    interaction = getattr(ui, "interaction", None) or getattr(ui, "source", None)
    if interaction is None:
        raise StaleStateError(user_message="Decision UI source missing.")

    decision = await sessions.get_decision(decision_id)
    if decision is None or decision.consumed:
        raise StaleStateError()
    if decision.expires_at and utcnow() >= decision.expires_at:
        label = "Idle" if decision.kind == "idle" else "Model"
        raise StaleStateError(user_message=f"{label} decision expired.")
    if str(ui.user.id) != decision.scope.user_id:
        raise AuthorizationError()

    spec = _DECISION_KINDS.get(decision.kind)
    if spec is None:
        raise StaleStateError()
    choice_s = choice.value if hasattr(choice, "value") else str(choice)
    if choice_s not in set(spec["choice_map"].values()):
        raise StaleStateError(user_message="Unknown decision choice.")

    pending = await sessions.get_pending_payload(decision_id)
    if not pending or not pending.get("prompt_text"):
        # Fail closed — consume so the control cannot be reused after restart.
        async with sessions.lock_for(decision.scope):
            decision = await sessions.get_decision(decision_id)
            if decision and not decision.consumed:
                decision.consumed = True
                decision.choice = spec["cancel_choice"]
                await sessions.save_decision(decision)
        await sessions.pop_pending_payload(decision_id)
        raise StaleStateError(
            user_message="Pending run payload missing after restart; please resubmit."
        )

    role_ids = _role_ids(ui.user)
    try:
        await _revalidate_run_auth(
            rt,
            user_id=decision.scope.user_id,
            guild_id=decision.scope.guild_id,
            channel_id=decision.scope.channel_id,
            role_ids=role_ids,
            subcommand="run",
            interaction=interaction,
        )
    except (AuthorizationError, ConfigurationError):
        async with sessions.lock_for(decision.scope):
            decision = await sessions.get_decision(decision_id)
            if decision and not decision.consumed:
                decision.consumed = True
                decision.choice = spec["cancel_choice"]
                await sessions.save_decision(decision)
        await sessions.pop_pending_payload(decision_id)
        if pending.get("retention_key"):
            await rt.access.images.discard(str(pending["retention_key"]))
        raise

    async with sessions.lock_for(decision.scope):
        decision = await sessions.get_decision(decision_id)
        if decision is None or decision.consumed:
            raise StaleStateError()
        decision.consumed = True
        decision.choice = choice_s
        await sessions.save_decision(decision)

    pending = await sessions.pop_pending_payload(decision_id) or pending
    await ui.notify(f"{spec['ack_label']}: `{choice_s}`.")
    if choice_s == spec["cancel_choice"]:
        if pending.get("retention_key"):
            await rt.access.images.discard(str(pending["retention_key"]))
        if getattr(interaction, "message", None):
            try:
                await interaction.message.edit(
                    content=f"### {spec['edit_label']} — cancelled", view=None
                )
            except discord.HTTPException:
                pass
        return

    active = await sessions.get_active(decision.scope)
    if active and active.thread_bound and choice_s == spec["new_session_choice"]:
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

    if getattr(interaction, "message", None):
        try:
            await interaction.message.edit(
                content=f"### {spec['edit_label']} — `{choice_s}`", view=None
            )
        except discord.HTTPException:
            pass

    # Resume stored PreparedRun context with one per-kind override.
    meta = dict(pending.get("prepared_meta") or {})
    reentry = dict(spec["reentry_kwargs"](choice_s))
    outcome = await prepare(
        rt,
        ui,
        pending.get("prompt") or pending["prompt_text"],
        pending.get("message_ref"),
        [],
        prebuilt=(
            pending["prompt_text"],
            images,
            list(pending.get("skipped") or []),
        ),
        thread_bound=bool(meta.get("thread_bound", False)),
        parent_channel_id=meta.get("parent_channel_id"),
        policy_channel_id=meta.get("policy_channel_id"),
        auth_subcommand=meta.get("subcommand"),
        **reentry,
    )
    if isinstance(outcome, PreparedRun):
        await launch(rt, ui, outcome)

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
            THREAD_THINKING_INDICATOR,
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
        rt = get_runtime()
        ui = as_launch_ui(interaction, client=rt.bot)
        outcome = await prepare(
            rt,
            ui,
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
        # Thread + approval/decision UI already show state; don't spam replies/ephemerals.
        # Slash `/cursor new` still gets a short ephemeral ack when launch starts immediately.
        if isinstance(outcome, (ApprovalPending, DecisionPending)):
            return
        await launch(rt, ui, outcome)
        if starter_message is None:
            await notify(f"Started Cursor session in {thread.mention}.")
    except CursorCloudError as exc:
        await _abandon_thread(exc.user_message)
        await notify(exc.user_message)
    except Exception as exc:
        logger.exception("cursor thread session failed")
        await _abandon_thread(str(exc))
        await notify(f"Thread session failed: {exc}")

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

    cfg = get_runtime().config
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
            get_runtime(),
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

    ui = ChannelUI.from_message(message, client=get_runtime().bot)
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
        interaction=ui,
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
