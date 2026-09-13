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

import logging
from typing import Any

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands as ext_commands

from cursor_cloud.access import AccessController, redact_preview
from cursor_cloud.config import DEFAULT_PLUGIN_CONFIG, load_cursor_config
from cursor_cloud.errors import (
    AuthorizationError,
    BusyRunError,
    ConfigurationError,
    CursorCloudError,
    OwnershipError,
    ValidationError,
)
from cursor_cloud.models import AccessTier, GitBranchInfo, RunStatus, ScopeKey
from cursor_cloud.run_log import (
    HISTORY_FOCUS_KINDS,
    format_history_message,
    sanitize_log_summary,
)
from cursor_cloud.run_tracker import RunTracker
from cursor_cloud.session_store import run_is_busy
from cursor_cloud.status_renderer import redact_untrusted
from modules.AI_manager import AI_Manager

from .discord_ui import (
    CONTENT_MENTIONS,
    DEFAULT_SONA_INSTRUCTIONS,
    InteractionUI,
    LaunchUI,
    as_launch_ui,
    build_sona_thread_system_instructions,
    _build_user_prompt,
    _channel_is_thread,
    _create_public_agent_thread,
    _defer,
    _ephemeral,
    _gate,
    _generate_session_title,
    _interaction_shim_for_channel,
    _interaction_shim_from_message,
    _live_prompt_manager,
    _live_sonata,
    _maybe_rename_thread,
    _policy_allowed,
    _policy_channel_id_from_interaction,
    _public,
    _resolve_policy_manager,
    _revalidate_run_auth,
    _role_ids,
    _role_ids_for_user,
    _runtime_chat_ai,
    _sanitize_thread_title,
    _scope_from_interaction,
    _scope_from_message,
    _title_from_prompt,
    _translate_thread_final_for_sona,
)
from .runtime import (
    CursorRuntime,
    cleanup_cursor_runtime,
    get_runtime,
    reset_runtime,
    set_runtime,
    setup_cursor_runtime,
)
from .workflows import (
    ApprovalPending,
    DecisionPending,
    PreparedRun,
    RunContext,
    complete_decision,
    finalize_session_from_snapshot,
    handle_agent_prefix,
    handle_component,
    handle_thread_message,
    launch,
    offer_decision,
    prepare,
    _build_context_for_run,
    _build_context_from_message,
    _launch_approved_request,
    _launch_run,
    _prepare_and_maybe_launch,
    _rehydrate_pending_images,
    _serializable_pending,
    _start_thread_bound_session,
)

logger = logging.getLogger("sonata.cursor")


# Re-exports used by tests (and importlib-loaded plugin surface).
from .runtime import (
    _edit_approval_expired_message,
    _expire_stale_decisions,
    _reconcile_runs,
    _register_views,
)


CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(
    lazy=True,
    config=dict(DEFAULT_PLUGIN_CONFIG),
)

__plugin_name__ = "cursor"

__dependencies__ = ["beacon", "chat"]

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
    rt = get_runtime()
    ui = InteractionUI(interaction)
    try:
        outcome = await prepare(
            rt,
            ui,
            prompt,
            message,
            [image1, image2, image3, image4, image5],
        )
        if isinstance(outcome, PreparedRun):
            await launch(rt, ui, outcome)
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)
    except Exception as exc:
        logger.exception("cursor run failed")
        await _ephemeral(interaction, f"Run failed: {exc}")

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
    sessions = get_runtime().sessions
    target_user_id = str(user.id) if user is not None else actor_scope.user_id
    emergency = user is not None and target_user_id != actor_scope.user_id
    if emergency:
        tier = await get_runtime().access.resolve_tier(interaction.user.id)
        if tier not in {AccessTier.GOD, AccessTier.ADMIN}:
            await _ephemeral(
                interaction,
                "Only Tier 0/1 may emergency-stop another user's owned session.",
            )
            return
        await get_runtime().access.audit(
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
            await get_runtime().client.cancel_run(active.agent_id, active.latest_run_id)
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
            branch = getattr(item, "branch", None) or "(branch)"
            pr = getattr(item, "pr_url", None)
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
    sessions = get_runtime().sessions
    items = list(await sessions.list_sessions(scope))
    # Thread-bound sessions live under the thread channel id. From a parent
    # channel, surface only threads rooted on *this* parent (not guild-wide).
    if not _channel_is_thread(getattr(interaction, "channel", None)):
        seen = {s.agent_id for s in items}
        try:
            for s in await sessions.all_sessions():
                if s.agent_id in seen:
                    continue
                if s.owner_id != scope.user_id:
                    continue
                if s.scope.guild_id != scope.guild_id:
                    continue
                if not s.thread_bound:
                    continue
                if str(s.parent_channel_id or "") != str(scope.channel_id):
                    continue
                items.append(s)
                seen.add(s.agent_id)
        except Exception:
            logger.debug(
                "Failed listing parent-channel thread sessions", exc_info=True
            )
    if not items:
        await _ephemeral(interaction, "No owned sessions in this channel.")
        return
    lines = ["### Sessions"]
    for s in items:
        mark = " (active)" if s.active else ""
        run = f" run `{s.latest_run_id}`" if s.latest_run_id else ""
        thread = ""
        if s.thread_bound:
            thread = f" thread `<#{s.scope.channel_id}>`"
        git_bits = []
        for item in list(s.latest_git or [])[:2]:
            branch = getattr(item, "branch", None)
            if branch:
                git_bits.append(str(branch))
        git = f" git `{', '.join(git_bits)}`" if git_bits else ""
        lines.append(
            f"- `{s.agent_id}` {redact_untrusted(s.name)[:40]} "
            f"[{s.latest_run_status.value}]{run}{thread}{git}{mark}"
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
        sessions = get_runtime().sessions
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
            await get_runtime().client.get_agent(target)
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
    sessions = get_runtime().sessions
    if not model_id:
        try:
            models = await get_runtime().client.list_models()
        except CursorCloudError as exc:
            await _ephemeral(interaction, exc.user_message)
            return
        preferred = (
            await sessions.get_model_pref(scope)
            or get_runtime().config.default_model
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
        models = await get_runtime().client.list_models()
        valid = {m.id for m in models}
        for m in models:
            valid.update(m.aliases)
        if model_id not in valid:
            await _ephemeral(interaction, f"Unknown model `{model_id}`.")
            return
        await sessions.set_model_pref(scope, model_id)
        active = await sessions.get_active(scope)
        if active is not None:
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
    sessions = get_runtime().sessions
    active = await sessions.get_active(scope)
    target_run = (run_id or "").strip() or (active.latest_run_id if active else None)
    if not target_run:
        await _ephemeral(interaction, "No active run. Pass `run_id` or start a run first.")
        return
    page_num = max(1, int(page or 1))
    page_size = 12
    logs = get_runtime().ensure_run_logs()
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
        tier = await get_runtime().access.resolve_tier(interaction.user.id)
        if tier not in {AccessTier.GOD, AccessTier.ADMIN}:
            await _ephemeral(
                interaction,
                "Only Tier 0/1 may emergency-status another user's owned session.",
            )
            return
        await get_runtime().access.audit(
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
    active = await get_runtime().sessions.get_active(scope)
    if active is None or not active.latest_run_id:
        await _ephemeral(interaction, "No active owned session/run.")
        return
    try:
        run = await get_runtime().client.get_run(active.agent_id, active.latest_run_id)
        active.latest_run_status = run.status
        git_payload = run.git if isinstance(run.git, dict) else None
        if git_payload:
            branches = GitBranchInfo.from_api_list(git_payload.get("branches") or [])
            if branches:
                active.latest_git = branches
        await get_runtime().sessions.upsert(active)
        await get_runtime().sessions.touch_activity(scope, active.agent_id)
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
                branch = getattr(item, "branch", None) or "(branch)"
                pr = getattr(item, "pr_url", None)
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
        await get_runtime().access.require_god(interaction.user.id)
        data = await get_runtime().access.list_assignments()
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
        resulting = await get_runtime().access.set_user_tier(interaction.user.id, user.id, tier)
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
        await get_runtime().access.require_god(interaction.user.id)
        grants = await get_runtime().access.store.list_grants()
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
        await get_runtime().access.revoke_grant(interaction.user.id, grant_id)
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
        await get_runtime().access.require_approver(interaction.user.id)
        pending_req = await get_runtime().access.store.get_request(request_id)
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
                    subcommand="run",
                    interaction=interaction,
                )
            except (AuthorizationError, ConfigurationError) as exc:
                await get_runtime().access.deny_unauthorized_request(
                    request_id,
                    actor_id=str(interaction.user.id),
                    reason=exc.user_message,
                )
                await _ephemeral(
                    interaction, f"Cannot approve: {exc.user_message}"
                )
                return
        request = await get_runtime().access.decide_request(
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
        await get_runtime().access.require_approver(interaction.user.id)
        request = await get_runtime().access.decide_request(
            interaction.user.id, request_id, mode="deny"
        )
        await _ephemeral(interaction, f"Request `{request_id}` → `{request.decision.value}`.")
    except CursorCloudError as exc:
        await _ephemeral(interaction, exc.user_message)

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

@MANAGER.builder
def cursor(sonata: AI_Manager):
    rt = get_runtime()
    cfg = load_cursor_config(CONTEXT.plugin_config)
    rt.config = cfg

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
            """Best-effort cleanup when discovered via Sonata (tests / legacy)."""
            await cleanup_cursor_runtime()

    return Cursor

@MANAGER.with_context(manager=True, client=True, config=True)
def cursor_register(context):
    """Register slash commands before first py-cord auto-sync (extend-time)."""
    bot = context.client
    sonata = context.manager
    rt = get_runtime()
    cfg = load_cursor_config(CONTEXT.plugin_config)
    rt.config = cfg
    if hasattr(sonata, "cursor"):
        sonata.cursor.config = cfg
    rt.bot = bot
    setattr(bot, "sonata", sonata)
    bot._cursor_runtime = rt
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

async def cursor_bot_hook(sonata: AI_Manager, bot: discord.Bot) -> None:
    """Invoked from SonataClient.on_ready for runtime/Beacon setup."""
    await setup_cursor_runtime(sonata, bot)

async def cursor_cleanup_hook(sonata=None, bot=None):
    """Memory-registered cleanup; production close uses bot._cursor_runtime."""
    runtime = getattr(bot, "_cursor_runtime", None) if bot is not None else None
    if runtime is not None:
        await runtime.aclose()
        return
    await cleanup_cursor_runtime()

@MANAGER.mem(
    {},
    key="cursor",
    hook=cursor_bot_hook,
    cleanup=cursor_cleanup_hook,
)
def init_cursor(_M):
    return None
