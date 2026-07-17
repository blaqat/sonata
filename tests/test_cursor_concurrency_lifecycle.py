"""Concurrency, lifecycle, component routing, and emergency path tests."""

from __future__ import annotations

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
    IdleDecision,
    ImageInput,
    ModelChoice,
    ModelDecision,
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
    from modules.AI_manager import AI_Manager

    path = ROOT / "src" / "modules" / "plugins" / "cursor-commands.py"
    spec = importlib.util.spec_from_file_location("cursor_commands_conc", path)
    module = importlib.util.module_from_spec(spec)
    previous = AI_Manager.M.MANAGER
    try:
        spec.loader.exec_module(module)
    finally:
        AI_Manager.M.MANAGER = previous
    return module


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
    mod._STATE.update(
        {
            "config": cfg,
            "sessions": sessions,
            "access_store": store,
            "access": access,
            "client": client,
            "cdn": MagicMock(aclose=AsyncMock()),
            "bot": None,
            "trackers": {},
            "policy_manager": PermissivePolicy(),
            "require_policy": False,
            "_cleanup_done": False,
        }
    )
    return sessions, access, cfg, client


def _interaction(user_id, *, guild_id=1, channel_id=2):
    user = SimpleNamespace(id=int(user_id), roles=[])
    response = MagicMock()
    response.is_done.return_value = False
    response.send_message = AsyncMock()
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
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T1)
        # Start idle (not busy); first submit marks CREATING under lock.
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

        release = asyncio.Event()
        submits = {"n": 0}

        async def slow_create_run(*args, **kwargs):
            submits["n"] += 1
            await release.wait()
            return SimpleNamespace(id="run-ok", status=RunStatus.CREATING)

        client.create_run = AsyncMock(side_effect=slow_create_run)

        public_msgs = []

        async def fake_public(interaction, content, **kwargs):
            msg = SimpleNamespace(
                id=len(public_msgs) + 1,
                channel=SimpleNamespace(id=2),
                content=content,
                edit=AsyncMock(),
                delete=AsyncMock(),
            )
            public_msgs.append(msg)
            return msg

        mod._public = fake_public

        class FakeTracker:
            def __init__(self, *a, **k):
                pass

            async def track(self, *a, **k):
                return SimpleNamespace(
                    status=RunStatus.FINISHED, degraded=False
                )

        with patch.object(mod, "RunTracker", FakeTracker):
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

            t1 = asyncio.create_task(launch())
            await asyncio.sleep(0.05)
            t2 = asyncio.create_task(launch())
            await asyncio.sleep(0.05)
            release.set()
            results = await asyncio.gather(t1, t2, return_exceptions=True)

        oks = [r for r in results if not isinstance(r, Exception)]
        busy = [r for r in results if isinstance(r, BusyRunError)]
        self.assertEqual(len(oks), 1, results)
        self.assertEqual(len(busy), 1, results)
        self.assertEqual(submits["n"], 1)
        # Busy pre-check under lock means the loser never posts Queued.
        self.assertEqual(len(public_msgs), 1)
        for m in public_msgs[1:]:
            self.assertTrue(m.delete.await_count or m.edit.await_count)


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

        with patch.object(
            mod,
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
            for d in state["idle"].values()
            if not d.get("consumed")
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
        await sessions.save_idle_decision(
            IdleDecision(
                decision_id="idle_r",
                scope=scope,
                agent_id="a1",
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
        await mod._complete_idle(interaction, "idle_r", IdleChoice.CANCEL)
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
        await sessions.save_idle_decision(
            IdleDecision(
                decision_id="idle_c",
                scope=scope,
                agent_id="a1",
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
        decision = await sessions.get_idle_decision("idle_c")
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
        await sessions.save_idle_decision(
            IdleDecision(
                decision_id="idle_dead",
                scope=scope,
                agent_id="a1",
                consumed=True,
                choice=IdleChoice.CANCEL,
            )
        )
        # Expired model
        await sessions.save_model_decision(
            ModelDecision(
                decision_id="mdl_exp",
                scope=scope,
                agent_id="a1",
                preferred_model="n",
                agent_model="o",
                expires_at=utcnow() - timedelta(minutes=1),
            )
        )
        await sessions.save_pending_payload("mdl_exp", {"prompt_text": "x"})
        # Valid idle with payload
        await sessions.save_idle_decision(
            IdleDecision(
                decision_id="idle_ok",
                scope=scope,
                agent_id="a1",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        await sessions.save_pending_payload(
            "idle_ok", {"prompt_text": "built", "image_metas": []}
        )
        # Multimodal missing retention after "restart"
        await sessions.save_idle_decision(
            IdleDecision(
                decision_id="idle_img",
                scope=scope,
                agent_id="a1",
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
        mod._STATE["bot"] = bot

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
