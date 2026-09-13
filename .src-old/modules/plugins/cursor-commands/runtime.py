"""Typed runtime owner, Beacon stores, and lifecycle loops for Cursor Discord."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar

import discord

from cursor_cloud.access import (
    AccessController,
    MemoryAccessStore,
    ImageRetentionStore,
)
from cursor_cloud.client import CursorCloudClient
from cursor_cloud.config import load_cursor_config
from cursor_cloud.discord_cdn import DiscordCDNDownloader
from cursor_cloud.models import (
    AgentSession,
    IdleChoice,
    PendingDecision,
    ScopeKey,
    utcnow,
)
from cursor_cloud.run_log import MemoryRunLogStore
from cursor_cloud.run_tracker import RunTracker
from cursor_cloud.session_store import (
    MemorySessionStore,
    run_is_busy,
    session_is_idle,
)
from cursor_cloud.status_renderer import initial_queued_message
from cursor_cloud.thread_sink import ThreadActivitySink
from modules.AI_manager import AI_Manager

logger = logging.getLogger("sonata.cursor")

HANDLED_THREAD_MESSAGES_MAX = 5000

_runtime: CursorRuntime | None = None


@dataclass
class CursorRuntime:
    """Single typed owner for Cursor plugin process state."""

    config: Any = None
    client: Any = None
    cdn: Any = None
    sessions: Any = None
    run_logs: Any = None
    access: Any = None
    bot: Any = None
    trackers: dict[str, asyncio.Task] = field(default_factory=dict)
    expiry_task: asyncio.Task | None = None
    reconcile_task: asyncio.Task | None = None
    policy_manager: Any = None
    handled_thread_messages: set[str] = field(default_factory=set)
    _handled_thread_message_order: deque[str] = field(
        default_factory=lambda: deque(maxlen=HANDLED_THREAD_MESSAGES_MAX),
        repr=False,
    )
    views_registered: bool = False
    closed: bool = False
    # Test / setup injectables (not always present in production).
    access_store: Any = None
    require_policy: bool | None = None

    def ensure_run_logs(self) -> MemoryRunLogStore:
        if self.run_logs is None:
            self.run_logs = MemoryRunLogStore()
        return self.run_logs

    def ensure_cdn(self) -> DiscordCDNDownloader:
        if self.cdn is None:
            max_bytes = (
                self.config.max_image_bytes if self.config else 15 * 1024 * 1024
            )
            self.cdn = DiscordCDNDownloader(max_bytes=max_bytes)
        return self.cdn

    def note_handled_thread_message(self, msg_id: str) -> bool:
        """Record ``msg_id`` with FIFO eviction. Return True if already seen."""
        if msg_id in self.handled_thread_messages:
            return True
        order = self._handled_thread_message_order
        if len(order) == order.maxlen:
            self.handled_thread_messages.discard(order[0])
        order.append(msg_id)
        self.handled_thread_messages.add(msg_id)
        return False

    def clear_handled_thread_messages(self) -> None:
        self.handled_thread_messages.clear()
        self._handled_thread_message_order.clear()

    async def aclose(self) -> None:
        """Cancel trackers/tasks and close shared HTTP clients (idempotent)."""
        if self.closed:
            return
        self.closed = True
        to_await: list[asyncio.Task] = []
        for attr in ("expiry_task", "reconcile_task"):
            task = getattr(self, attr)
            if task is not None:
                task.cancel()
                to_await.append(task)
                setattr(self, attr, None)
        for agent_id, task in list(self.trackers.items()):
            task.cancel()
            to_await.append(task)
            self.trackers.pop(agent_id, None)
        if to_await:
            await asyncio.gather(*to_await, return_exceptions=True)
        client = self.client
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.exception("Cursor client close failed")
            self.client = None
        cdn = self.cdn
        if cdn is not None:
            try:
                await cdn.aclose()
            except Exception:
                logger.exception("Cursor CDN client close failed")
            self.cdn = None
        self.views_registered = False


def get_runtime() -> CursorRuntime:
    """Return the process-wide runtime, creating an empty one if needed."""
    global _runtime
    if _runtime is None:
        _runtime = CursorRuntime()
    return _runtime


def set_runtime(runtime: CursorRuntime | None) -> None:
    """Install or clear the process-wide runtime (tests / setup)."""
    global _runtime
    _runtime = runtime


def reset_runtime(**kwargs: Any) -> CursorRuntime:
    """Replace the process-wide runtime with a fresh instance (tests)."""
    rt = CursorRuntime(**kwargs)
    set_runtime(rt)
    return rt

class BeaconBacked:
    """Mixin: load/persist Memory* store state via a Beacon branch key."""

    _beacon_key: ClassVar[str]
    _beacon_label: ClassVar[str]

    beacon: Any

    def _init_beacon(self, beacon_branch) -> None:
        self.beacon = beacon_branch
        self._load()

    def _load(self) -> None:
        try:
            data = self.beacon.discover(self._beacon_key)
            if isinstance(data, dict):
                self.import_state(data)
        except Exception:
            logger.exception(
                "Failed loading Cursor %s from Beacon", self._beacon_label
            )

    def _persist(self) -> None:
        try:
            self.beacon.illuminate(self._beacon_key, self.export_state())
        except Exception:
            logger.exception(
                "Failed persisting Cursor %s", self._beacon_label
            )


class BeaconSessionStore(BeaconBacked, MemorySessionStore):
    _beacon_key = "sessions"
    _beacon_label = "sessions"

    def __init__(self, beacon_branch, *, max_recent: int = 20):
        super().__init__(max_recent=max_recent)
        self._init_beacon(beacon_branch)

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

    async def save_decision(self, decision: PendingDecision) -> PendingDecision:
        result = await super().save_decision(decision)
        self._persist()
        return result

    async def reserve_decision(
        self, decision: PendingDecision
    ) -> PendingDecision | None:
        result = await super().reserve_decision(decision)
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


class BeaconRunLogStore(BeaconBacked, MemoryRunLogStore):
    _beacon_key = "run_logs"
    _beacon_label = "run logs"

    def __init__(self, beacon_branch, **kwargs):
        super().__init__(**kwargs)
        self._init_beacon(beacon_branch)

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


class BeaconAccessStore(BeaconBacked, MemoryAccessStore):
    _beacon_key = "access"
    _beacon_label = "access"

    def __init__(self, beacon_branch, *, audit_limit: int = 200):
        super().__init__(audit_limit=audit_limit)
        self._init_beacon(beacon_branch)

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

async def _discard_retention_key(key: str | None) -> None:
    if key:
        await get_runtime().access.images.discard(str(key))

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
    access = get_runtime().access
    if access is None:
        return False
    images = await access.images.get(str(key))
    return bool(images)

async def _register_views(bot: discord.Bot) -> None:
    """Re-register durable non-ephemeral views; skip consumed/expired/unrehydratable."""
    from .discord_ui import ApprovalView
    from .workflows import _DECISION_KINDS

    rt = get_runtime()
    access = rt.access
    sessions = rt.sessions
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
        for decision_id, raw in (state.get("decisions") or {}).items():
            try:
                decision = PendingDecision.from_dict(raw)
            except Exception:
                continue
            if decision.consumed:
                continue
            if decision.expires_at and now >= decision.expires_at:
                continue
            pending = await sessions.get_pending_payload(decision_id)
            if not await _pending_rehydratable(pending):
                continue
            spec = _DECISION_KINDS.get(decision.kind)
            if spec is None:
                continue
            bot.add_view(spec["view_factory"](decision_id))
    rt.views_registered = True

async def _reconcile_runs() -> None:
    from .discord_ui import CONTENT_MENTIONS, DiscordStatusSink, _translate_thread_final_for_sona
    from .workflows import finalize_session_from_snapshot

    rt = get_runtime()
    client = rt.client
    sessions = rt.sessions
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
                bot = rt.bot
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
                        edit_interval_ms=rt.config.status_edit_interval_ms,
                        allowed_mentions=CONTENT_MENTIONS,
                        final_translator=_translate_thread_final_for_sona,
                    )
                else:
                    sink = DiscordStatusSink(msg)
                tracker = RunTracker(
                    client,
                    sink,
                    edit_interval_ms=rt.config.status_edit_interval_ms,
                    agent_name=session.name or session.agent_id,
                    run_log=rt.ensure_run_logs(),
                    scope=session.scope,
                )

                async def _resume(sess=session, tr=tracker, sk=sink):
                    snap = await tr.track(
                        sess.agent_id,
                        sess.latest_run_id,
                        initial_status=sess.latest_run_status,
                    )
                    finalize_session_from_snapshot(sess, snap, sink=sk)
                    await sessions.upsert(sess)

                rt.trackers[session.agent_id] = asyncio.create_task(_resume())
        except Exception:
            logger.exception("Cursor reconcile failed for %s", session.agent_id)

async def _edit_approval_expired_message(request) -> None:
    from .discord_ui import CONTENT_MENTIONS

    bot = get_runtime().bot
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
    from .discord_ui import CONTENT_MENTIONS
    from .workflows import _DECISION_KINDS

    bot = get_runtime().bot
    if not bot or not channel_id or not message_id:
        return
    spec = _DECISION_KINDS.get(kind) or {}
    label = spec.get("expired_label") or ("Idle session" if kind == "idle" else "Model choice")
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
    from .workflows import _DECISION_KINDS

    rt = get_runtime()
    sessions = rt.sessions
    access = rt.access
    if not sessions:
        return
    now = utcnow()
    state = sessions.export_state()
    for decision_id, raw in list((state.get("decisions") or {}).items()):
        try:
            decision = PendingDecision.from_dict(raw)
        except Exception:
            continue
        if decision.consumed:
            continue
        if decision.expires_at and now >= decision.expires_at:
            spec = _DECISION_KINDS.get(decision.kind) or {}
            decision.consumed = True
            decision.choice = spec.get("cancel_choice") or IdleChoice.CANCEL.value
            await sessions.save_decision(decision)
            pending = await sessions.pop_pending_payload(decision_id)
            if pending:
                await _discard_retention_key(pending.get("retention_key"))
            await _edit_decision_expired_message(
                kind=decision.kind,
                decision_id=decision_id,
                channel_id=decision.message_channel_id,
                message_id=decision.message_id,
            )
    if access:
        await access.images.purge_expired()

async def _archive_idle_threads() -> None:
    """Archive bound threads after session idle (Discord min native archive is 60m)."""
    from .discord_ui import _channel_is_thread

    rt = get_runtime()
    cfg = rt.config
    sessions = rt.sessions
    bot = rt.bot
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
            rt = get_runtime()
            if rt.access:
                expired = await rt.access.expire_stale_requests()
                for request in expired:
                    await _edit_approval_expired_message(request)
            await _expire_stale_decisions()
            await _archive_idle_threads()
        except Exception:
            logger.exception("Cursor approval expiry loop failed")
        await asyncio.sleep(60)

async def cleanup_cursor_runtime() -> None:
    """Idempotent shutdown via ``CursorRuntime.aclose``."""
    await get_runtime().aclose()

async def setup_cursor_runtime(sonata: AI_Manager, bot: discord.Bot) -> None:
    from .module import CONTEXT, _register_commands

    rt = get_runtime()
    if rt.closed:
        rt = CursorRuntime()
        set_runtime(rt)
    rt.closed = False

    cfg = load_cursor_config(CONTEXT.plugin_config)
    rt.config = cfg
    rt.bot = bot
    setattr(bot, "sonata", sonata)
    # Single discovery attribute for SonataClient.close (F2).
    bot._cursor_runtime = rt
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

    rt.sessions = sessions
    rt.run_logs = run_logs
    rt.access_store = access_store
    rt.access = AccessController(
        cfg,
        access_store,
        image_retention=ImageRetentionStore(max_total_bytes=cfg.max_retained_image_bytes),
    )
    old = rt.client
    rt.client = CursorCloudClient(cfg)
    if old is not None:
        try:
            await old.aclose()
        except Exception:
            pass

    old_cdn = rt.cdn
    rt.cdn = DiscordCDNDownloader(max_bytes=cfg.max_image_bytes)
    if old_cdn is not None:
        try:
            await old_cdn.aclose()
        except Exception:
            pass

    await _register_views(bot)

    if cfg.is_ready:
        if rt.reconcile_task is None or rt.reconcile_task.done():
            rt.reconcile_task = asyncio.create_task(_reconcile_runs())
        if rt.expiry_task is None or rt.expiry_task.done():
            rt.expiry_task = asyncio.create_task(_expiry_loop())
