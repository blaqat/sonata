"""Concurrency, lifecycle, component routing, and emergency path tests."""

from __future__ import annotations
from contextlib import contextmanager

import asyncio
import importlib.util
import pathlib
import sys
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.access import AccessController, ImageRetentionStore, MemoryAccessStore
from cursor_cloud.config import load_cursor_config
from cursor_cloud.errors import BusyRunError
from cursor_cloud.models import (
    AccessTier,
    AgentSession,
    ApprovalDecision,
    IdleChoice,
    ImageInput,
    ModelChoice,
    PendingDecision,
    RunRequestEnvelope,
    RunStatus,
    ScopeKey,
    utcnow,
)
from cursor_cloud.session_store import MemorySessionStore


GOD = "100000000000000001"
T1 = "100000000000000002"
T2 = "100000000000000003"


def load_cursor_plugin():
    import importlib

    from modules.AI_manager import AI_Manager

    pkg = "modules.plugins.cursor-commands"
    previous = AI_Manager.M.MANAGER
    try:
        for key in list(sys.modules):
            if key == pkg or key.startswith(pkg + "."):
                del sys.modules[key]
        mod = importlib.import_module(pkg + ".module")
        mod.discord_ui = sys.modules[pkg + ".discord_ui"]
        mod.workflows = sys.modules[pkg + ".workflows"]
        mod.runtime = sys.modules[pkg + ".runtime"]
        return mod
    finally:
        AI_Manager.M.MANAGER = previous


@contextmanager
def patch_cursor(mod, name, *args, **kwargs):
    """Patch ``name`` on the plugin module and owning package submodules.

    Yields the mock/object from the primary (plugin module) patch when present,
    matching ``patch.object`` ``as`` semantics.
    """
    from contextlib import ExitStack
    from unittest.mock import patch

    targets = []
    for m in (
        mod,
        getattr(mod, "discord_ui", None),
        getattr(mod, "workflows", None),
        getattr(mod, "runtime", None),
    ):
        if m is not None and hasattr(m, name):
            targets.append(m)
    with ExitStack() as stack:
        primary = None
        for i, m in enumerate(targets):
            cm = patch.object(m, name, *args, **kwargs)
            val = stack.enter_context(cm)
            if i == 0:
                primary = val
        yield primary





class PermissivePolicy:
    def can_speak(self, **kwargs):
        return True

    def is_command_allowed(self, **kwargs):
        return True


def _bootstrap(mod):
    cfg = load_cursor_config(
        {
            "enabled": True,
            "default_repository_url": "https://github.com/o/r",
            "session_idle_prompt_minutes": 10,
            "access": {"tier1_user_ids": [T1], "tier2_user_ids": [T2]},
        },
        env={"CURSOR_API_KEY": "k", "GOD": GOD},
    )
    sessions = MemorySessionStore()
    store = MemoryAccessStore()
    access = AccessController(
        cfg, store, image_retention=ImageRetentionStore(max_total_bytes=5_000_000)
    )
    client = MagicMock()
    client.create_agent = AsyncMock(
        return_value=(
            SimpleNamespace(id="bc-new", name="n", model="m"),
            SimpleNamespace(id="run-new", status=RunStatus.CREATING),
        )
    )
    client.create_run = AsyncMock(
        return_value=SimpleNamespace(id="run-f", status=RunStatus.CREATING)
    )
    client.cancel_run = AsyncMock()
    client.get_run = AsyncMock(
        return_value=SimpleNamespace(
            id="run-1", status=RunStatus.RUNNING, result=None, duration_ms=None, git=None
        )
    )
    client.aclose = AsyncMock()
    mod.reset_runtime(
        config=cfg,
        sessions=sessions,
        access_store=store,
        access=access,
        client=client,
        cdn=MagicMock(aclose=AsyncMock()),
        bot=None,
        trackers={},
        policy_manager=PermissivePolicy(),
        require_policy=False,
    )
    return sessions, access, cfg, client


def _interaction(user_id, *, guild_id=1, channel_id=2):
    user = SimpleNamespace(id=int(user_id), roles=[])
    response = MagicMock()
    response.is_done.return_value = False
    response.send_message = AsyncMock()
    response.defer = AsyncMock()
    followup = MagicMock()
    followup.send = AsyncMock()
    channel = MagicMock()
    channel.id = channel_id
    posted = []

    async def send(content, **kwargs):
        msg = SimpleNamespace(
            id=1000 + len(posted),
            channel=SimpleNamespace(id=channel_id),
            content=content,
            edit=AsyncMock(),
            delete=AsyncMock(),
        )
        posted.append(msg)
        return msg

    channel.send = AsyncMock(side_effect=send)
    guild = MagicMock()
    guild.get_channel.return_value = channel
    guild.get_member.return_value = None
    interaction = SimpleNamespace(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        channel=channel,
        guild=guild,
        client=SimpleNamespace(sonata=None, fetch_channel=AsyncMock(return_value=channel)),
        response=response,
        followup=followup,
        message=None,
        data={},
        id=123,
        _posted=posted,
    )
    return interaction


class TestNoOrphanBusyStatus(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_launch_busy_no_orphan_and_one_submit(self):
        """Slow _public widens TOCTOU: both may post; loser status cleaned; 1 submit."""
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T1)
        await sessions.upsert(
            AgentSession(
                scope=scope,
                agent_id="a1",
                owner_id=T1,
                active=True,
                latest_run_id="r0",
                latest_run_status=RunStatus.FINISHED,
            )
        )

        submits = {"n": 0}
        public_gate = asyncio.Event()
        public_entered = {"n": 0}
        public_msgs = []

        async def slow_create_run(*args, **kwargs):
            submits["n"] += 1
            return SimpleNamespace(id="run-ok", status=RunStatus.CREATING)

        client.create_run = AsyncMock(side_effect=slow_create_run)

        async def slow_post_status(self, content, **kwargs):
            public_entered["n"] += 1
            # Block until both callers have entered post_status (deterministic TOCTOU).
            if public_entered["n"] >= 2:
                public_gate.set()
            await public_gate.wait()
            await asyncio.sleep(0)  # yield so both proceed into submit lock
            msg = SimpleNamespace(
                id=len(public_msgs) + 1,
                channel=SimpleNamespace(id=2),
                content=content,
                edit=AsyncMock(),
                delete=AsyncMock(),
            )
            public_msgs.append(msg)
            return msg

        mod.InteractionUI.post_status = slow_post_status

        class FakeTracker:
            def __init__(self, *a, **k):
                pass

            async def track(self, *a, **k):
                return SimpleNamespace(status=RunStatus.FINISHED, degraded=False)

        with patch_cursor(mod, "RunTracker", FakeTracker):
            async def launch():
                interaction = _interaction(T1)
                return await mod._launch_run(
                    interaction,
                    prompt_text="p",
                    images=[],
                    skipped=[],
                    agent_id="a1",
                    force_new=False,
                    model="m",
                    scope=scope,
                    role_ids=[],
                )

            results = await asyncio.gather(
                asyncio.create_task(launch()),
                asyncio.create_task(launch()),
                return_exceptions=True,
            )

        oks = [r for r in results if not isinstance(r, Exception)]
        busy = [r for r in results if isinstance(r, BusyRunError)]
        self.assertEqual(len(oks), 1, results)
        self.assertEqual(len(busy), 1, results)
        self.assertEqual(submits["n"], 1)
        self.assertEqual(len(public_msgs), 2)
        cleaned = [
            m
            for m in public_msgs
            if m.delete.await_count
            or (m.edit.await_count and "Busy" in str(m.edit.await_args))
        ]
        self.assertGreaterEqual(len(cleaned), 1)

    async def test_busy_before_grant_consume_no_consume(self):
        """Busy rejection must happen before one-run grant consume."""
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        await sessions.upsert(
            AgentSession(
                scope=scope,
                agent_id="a1",
                owner_id=T2,
                active=True,
                latest_run_id="r0",
                latest_run_status=RunStatus.RUNNING,
            )
        )
        env = RunRequestEnvelope(
            requester_id=T2,
            scope=scope,
            prompt_text="p",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id="a1",
            is_follow_up=True,
        )
        req = await access.create_approval_request(env, prompt_preview="p")
        req = await access.decide_request(GOD, req.request_id, mode="once")
        grant = await access.store.get_grant(req.grant_id)
        self.assertFalse(grant.consumed)

        interaction = _interaction(T2)
        with self.assertRaises(BusyRunError):
            await mod._launch_run(
                interaction,
                prompt_text="p",
                images=[],
                skipped=[],
                agent_id="a1",
                force_new=False,
                model="m",
                grant=grant,
                envelope=env,
                scope=scope,
                role_ids=[],
                skip_status_post=True,
            )
        grant2 = await access.store.get_grant(req.grant_id)
        self.assertFalse(grant2.consumed)
        client.create_run.assert_not_awaited()

    async def test_busy_after_consume_marks_submit_failed(self):
        """If busy is detected after consume, audit submit-failed-after-consume."""
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        await sessions.upsert(
            AgentSession(
                scope=scope,
                agent_id="a1",
                owner_id=T2,
                active=True,
                latest_run_id="r0",
                latest_run_status=RunStatus.FINISHED,
            )
        )
        env = RunRequestEnvelope(
            requester_id=T2,
            scope=scope,
            prompt_text="p",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id="a1",
            is_follow_up=True,
        )
        req = await access.create_approval_request(env, prompt_preview="p")
        req = await access.decide_request(GOD, req.request_id, mode="once")
        grant = await access.store.get_grant(req.grant_id)

        # Flip to busy after consume by patching get_session.
        real_get = sessions.get_session
        calls = {"n": 0}

        async def flaky_get(scope_key, agent_id):
            sess = await real_get(scope_key, agent_id)
            calls["n"] += 1
            # 1=pre-check, 2=pre-consume busy check → still free.
            # 3=post-consume defensive busy check → busy.
            if calls["n"] >= 3 and sess is not None:
                sess.latest_run_status = RunStatus.RUNNING
            return sess

        sessions.get_session = flaky_get
        interaction = _interaction(T2)
        with self.assertRaises(BusyRunError):
            await mod._launch_run(
                interaction,
                prompt_text="p",
                images=[],
                skipped=[],
                agent_id="a1",
                force_new=False,
                model="m",
                grant=grant,
                envelope=env,
                scope=scope,
                role_ids=[],
                skip_status_post=True,
            )
        grant2 = await access.store.get_grant(req.grant_id)
        self.assertTrue(grant2.consumed)
        events = await access.store.list_audit(limit=20)
        self.assertTrue(any(e.action == "submit_failed_after_consume" for e in events))
        client.create_run.assert_not_awaited()


class TestIdleDecisionDedupe(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_idle_offers_one_decision(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        await sessions.upsert(
            AgentSession(
                scope=scope,
                agent_id="a1",
                owner_id=T2,
                model="m",
                active=True,
                last_meaningful_activity_at=utcnow() - timedelta(minutes=11),
            )
        )

        sends = {"n": 0}

        async def counting_prepare(interaction, *args, **kwargs):
            # Call real offer path via prepare
            return await mod._prepare_and_maybe_launch(interaction, *args, **kwargs)

        with patch_cursor(mod,
            "_build_context_for_run",
            AsyncMock(return_value=("built", [], [])),
        ):
            async def one():
                inter = _interaction(T2)
                await mod._prepare_and_maybe_launch(inter, "hi", None, [], skip_model=True)
                return inter

            r1, r2 = await asyncio.gather(one(), one())
        state = sessions.export_state()
        open_idle = [
            d
            for d in state["decisions"].values()
            if d.get("kind") == "idle" and not d.get("consumed")
        ]
        self.assertEqual(len(open_idle), 1)
        # Only one channel decision message (second gets ephemeral dedupe).
        total_sends = len(r1._posted) + len(r2._posted)
        self.assertEqual(total_sends, 1)


class TestRetentionDiscard(unittest.IsolatedAsyncioTestCase):
    async def test_idle_cancel_discards_retention(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        img = ImageInput(mime_type="image/png", data_b64="AAAA", size_bytes=3)
        await access.images.put("ret_x", [img], expires_at=utcnow() + timedelta(hours=1))
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_r",
                scope=scope,
                agent_id="a1",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        await sessions.save_pending_payload(
            "idle_r",
            {
                "prompt_text": "built",
                "prompt": "p",
                "retention_key": "ret_x",
                "image_metas": [],
            },
        )
        interaction = _interaction(T2)
        await mod.complete_decision(
            mod.get_runtime(),
            mod.InteractionUI(interaction),
            "idle_r",
            IdleChoice.CANCEL.value,
        )
        self.assertIsNone(await access.images.get("ret_x"))


class TestEmergencyHandlers(unittest.IsolatedAsyncioTestCase):
    async def test_cursor_stop_emergency_tier0_audited(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        victim = ScopeKey("1", "2", T2)
        await sessions.upsert(
            AgentSession(
                scope=victim,
                agent_id="a1",
                owner_id=T2,
                active=True,
                latest_run_id="r1",
                latest_run_status=RunStatus.RUNNING,
            )
        )
        interaction = _interaction(GOD)
        ctx = SimpleNamespace(interaction=interaction)
        target = SimpleNamespace(id=int(T2))
        await mod.cursor_stop(ctx, user=target)
        client.cancel_run.assert_awaited()
        events = await access.store.list_audit(limit=10)
        self.assertTrue(any(e.action == "emergency_stop" for e in events))

    async def test_cursor_stop_tier2_cannot_emergency(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        victim = ScopeKey("1", "2", T1)
        await sessions.upsert(
            AgentSession(
                scope=victim,
                agent_id="a1",
                owner_id=T1,
                active=True,
                latest_run_id="r1",
                latest_run_status=RunStatus.RUNNING,
            )
        )
        interaction = _interaction(T2)
        ctx = SimpleNamespace(interaction=interaction)
        await mod.cursor_stop(ctx, user=SimpleNamespace(id=int(T1)))
        client.cancel_run.assert_not_awaited()

    async def test_cursor_status_emergency_tier1(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        victim = ScopeKey("1", "2", T2)
        await sessions.upsert(
            AgentSession(
                scope=victim,
                agent_id="a1",
                owner_id=T2,
                active=True,
                latest_run_id="r1",
                latest_run_status=RunStatus.RUNNING,
            )
        )
        interaction = _interaction(T1)
        # status posts publicly when no status message ids
        interaction.response.is_done.return_value = True
        interaction.followup.send = AsyncMock(
            return_value=SimpleNamespace(id=1, channel=SimpleNamespace(id=2))
        )
        ctx = SimpleNamespace(interaction=interaction)
        await mod.cursor_status(ctx, user=SimpleNamespace(id=int(T2)))
        client.get_run.assert_awaited()
        events = await access.store.list_audit(limit=10)
        self.assertTrue(any(e.action == "emergency_status" for e in events))


class TestHandleComponentAndViews(unittest.IsolatedAsyncioTestCase):
    async def test_handle_component_idle_revalidates(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_c",
                scope=scope,
                agent_id="a1",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        await sessions.save_pending_payload(
            "idle_c",
            {"prompt_text": "built", "prompt": "p", "skipped": [], "image_metas": []},
        )
        await access.set_user_tier(GOD, T2, "3")
        interaction = _interaction(T2)
        interaction.data = {"custom_id": "c105:idle_cont:idle_c"}
        ok = await mod.handle_component(interaction)
        self.assertTrue(ok)
        decision = await sessions.get_decision("idle_c")
        self.assertTrue(decision.consumed)

    async def test_register_views_skips_expired_consumed_missing_payload(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        # Valid pending approval
        env = RunRequestEnvelope(
            requester_id=T2,
            scope=scope,
            prompt_text="p",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
        )
        req = await access.create_approval_request(env, prompt_preview="p", images=[])
        # Consumed idle
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_dead",
                scope=scope,
                agent_id="a1",
                kind="idle",
                consumed=True,
                choice=IdleChoice.CANCEL.value,
            )
        )
        # Expired model
        await sessions.save_decision(
            PendingDecision(
                decision_id="mdl_exp",
                scope=scope,
                agent_id="a1",
                kind="model",
                expires_at=utcnow() - timedelta(minutes=1),
                extras={"preferred_model": "n", "agent_model": "o"},
            )
        )
        await sessions.save_pending_payload("mdl_exp", {"prompt_text": "x"})
        # Valid idle with payload
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_ok",
                scope=scope,
                agent_id="a1",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        await sessions.save_pending_payload(
            "idle_ok", {"prompt_text": "built", "image_metas": []}
        )
        # Multimodal missing retention after "restart"
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_img",
                scope=scope,
                agent_id="a1",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        await sessions.save_pending_payload(
            "idle_img",
            {
                "prompt_text": "built",
                "retention_key": "missing",
                "image_metas": [{"mime_type": "image/png", "fingerprint": "x"}],
            },
        )

        bot = MagicMock()
        views = []
        bot.add_view.side_effect = lambda v: views.append(v)
        await mod._register_views(bot)
        kinds = {type(v).__name__ for v in views}
        self.assertIn("ApprovalView", kinds)
        self.assertIn("IdleDecisionView", kinds)
        # Only idle_ok should be registered among idles
        idle_ids = [
            getattr(v, "decision_id", None)
            or (v.children[0].custom_id.split(":")[-1] if getattr(v, "children", None) else None)
            for v in views
            if type(v).__name__ == "IdleDecisionView"
        ]
        # custom_id embeds decision id
        custom_ids = []
        for v in views:
            if type(v).__name__ == "IdleDecisionView":
                for item in v.children:
                    custom_ids.append(item.custom_id)
        self.assertTrue(any("idle_ok" in c for c in custom_ids))
        self.assertFalse(any("idle_dead" in c for c in custom_ids))
        self.assertFalse(any("idle_img" in c for c in custom_ids))
        self.assertFalse(any("mdl_exp" in c for c in custom_ids))


class TestExpiryAndReconcile(unittest.IsolatedAsyncioTestCase):
    async def test_idle_decision_expiry_edits_channel_message(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        decision = PendingDecision(
            decision_id="idle_exp",
            scope=scope,
            agent_id="a1",
            kind="idle",
            expires_at=utcnow() - timedelta(seconds=1),
            message_channel_id="2",
            message_id="55",
        )
        await sessions.save_decision(decision)
        await sessions.save_pending_payload(
            "idle_exp",
            {"prompt_text": "built", "retention_key": None, "image_metas": []},
        )
        msg = MagicMock()
        msg.edit = AsyncMock()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        bot = MagicMock()
        bot.get_channel.return_value = channel
        mod.get_runtime().bot = bot

        await mod._expire_stale_decisions()
        again = await sessions.get_decision("idle_exp")
        self.assertTrue(again.consumed)
        self.assertIsNone(await sessions.get_pending_payload("idle_exp"))
        msg.edit.assert_awaited()
        kwargs = msg.edit.await_args.kwargs
        self.assertIsNone(kwargs.get("view"))
        self.assertIn("Expired", kwargs.get("content") or "")

    async def test_edit_approval_expired_message(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        env = RunRequestEnvelope(
            requester_id=T2,
            scope=ScopeKey("1", "2", T2),
            prompt_text="p",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
        )
        req = await access.create_approval_request(env, prompt_preview="p")
        req.approval_channel_id = "2"
        req.approval_message_id = "99"
        req.expires_at = utcnow() - timedelta(seconds=1)
        await access.store.save_request(req)

        msg = MagicMock()
        msg.edit = AsyncMock()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(return_value=msg)
        bot = MagicMock()
        bot.get_channel.return_value = channel
        mod.get_runtime().bot = bot

        expired = await access.expire_stale_requests()
        self.assertEqual(len(expired), 1)
        await mod._edit_approval_expired_message(expired[0])
        msg.edit.assert_awaited()
        kwargs = msg.edit.await_args.kwargs
        self.assertIsNone(kwargs.get("view"))
        self.assertIn("Expired", kwargs.get("content") or msg.edit.await_args.args[0])

    async def test_reconcile_busy_run_polls_without_network_tracker(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T1)
        await sessions.upsert(
            AgentSession(
                scope=scope,
                agent_id="a1",
                owner_id=T1,
                active=True,
                latest_run_id="r1",
                latest_run_status=RunStatus.RUNNING,
                status_channel_id="2",
                status_message_id="9",
            )
        )
        client.get_run = AsyncMock(
            return_value=SimpleNamespace(
                id="r1",
                status=RunStatus.FINISHED,
                result="done",
                duration_ms=1,
                git=None,
            )
        )
        # FINISHED is not active — reconcile updates status and does not resume tracker
        await mod._reconcile_runs()
        session = await sessions.get_session(scope, "a1")
        self.assertEqual(session.latest_run_status, RunStatus.FINISHED)
        client.get_run.assert_awaited()


if __name__ == "__main__":
    unittest.main()
