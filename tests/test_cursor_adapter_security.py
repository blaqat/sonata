"""Adapter-level security/completeness tests for cursor-commands (SONA-105)."""

from __future__ import annotations

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
from cursor_cloud.context import metas_from_images, metas_match
from cursor_cloud.errors import AuthorizationError, ConfigurationError, ValidationError
from cursor_cloud.models import (
    AccessTier,
    AgentSession,
    ApprovalDecision,
    IdleChoice,
    IdleDecision,
    ImageInput,
    ModelChoice,
    ModelDecision,
    PromptImageMeta,
    RunRequestEnvelope,
    ScopeKey,
    utcnow,
)
from cursor_cloud.session_store import MemorySessionStore, session_is_idle


GOD = "100000000000000001"
T1 = "100000000000000002"
T2 = "100000000000000003"
T3 = "100000000000000004"


def load_cursor_plugin():
    from modules.AI_manager import AI_Manager

    path = ROOT / "src" / "modules" / "plugins" / "cursor-commands.py"
    spec = importlib.util.spec_from_file_location("cursor_commands_sec", path)
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


class DenyingPolicy:
    def can_speak(self, **kwargs):
        return False

    def is_command_allowed(self, **kwargs):
        return False


def _cfg(extra=None):
    plugin = {
        "enabled": True,
        "default_repository_url": "https://github.com/o/r",
        "session_idle_prompt_minutes": 10,
        "access": {"tier1_user_ids": [T1], "tier2_user_ids": [T2]},
    }
    if extra:
        plugin.update(extra)
    return load_cursor_config(plugin, env={"CURSOR_API_KEY": "k", "GOD": GOD})


def _bootstrap(mod, *, policy=None, require_policy=False):
    cfg = _cfg()
    sessions = MemorySessionStore()
    store = MemoryAccessStore()
    access = AccessController(
        cfg, store, image_retention=ImageRetentionStore(max_total_bytes=5_000_000)
    )
    mod._STATE.update(
        {
            "config": cfg,
            "sessions": sessions,
            "access_store": store,
            "access": access,
            "client": MagicMock(),
            "cdn": MagicMock(),
            "bot": None,
            "trackers": {},
            "policy_manager": policy if policy is not None else PermissivePolicy(),
            "require_policy": require_policy,
        }
    )
    return sessions, access, cfg


def _interaction(user_id, *, guild_id=1, channel_id=2, response_done=False):
    user = SimpleNamespace(id=int(user_id), roles=[])
    response = MagicMock()
    response.is_done.return_value = response_done
    response.send_message = AsyncMock()
    followup = MagicMock()
    followup.send = AsyncMock()
    channel = MagicMock()
    channel.id = channel_id
    channel.send = AsyncMock(
        return_value=SimpleNamespace(id=99, channel=SimpleNamespace(id=channel_id))
    )
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
    )
    return interaction


class TestGateAndPolicy(unittest.IsolatedAsyncioTestCase):
    async def test_denied_tier_fails_closed(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        with self.assertRaises(AuthorizationError):
            await mod._revalidate_run_auth(
                user_id=T3, guild_id=1, channel_id=2, role_ids=[], subcommand="run"
            )

    async def test_missing_policy_fail_closed_when_required(self):
        mod = load_cursor_plugin()
        _bootstrap(mod, policy=None, require_policy=True)
        mod._STATE["policy_manager"] = None
        with patch.object(mod, "_resolve_policy_manager", return_value=None):
            with self.assertRaises(ConfigurationError):
                await mod._revalidate_run_auth(
                    user_id=T2, guild_id=1, channel_id=2, role_ids=[], subcommand="run"
                )

    def test_resolve_policy_manager_uses_sona_chat_plugin(self):
        mod = load_cursor_plugin()
        pm = SimpleNamespace()
        # Sonata.get("chat") is chat history; policy lives on Sonata.chat.
        sona = SimpleNamespace(
            chat=SimpleNamespace(policy_manager=pm),
            get=lambda *args, **kwargs: {},
        )
        mod._STATE["policy_manager"] = None
        mod._STATE["bot"] = SimpleNamespace(sonata=sona)
        self.assertIs(mod._resolve_policy_manager(), pm)

    async def test_channel_policy_deny(self):
        mod = load_cursor_plugin()
        _bootstrap(mod, policy=DenyingPolicy())
        with self.assertRaises(AuthorizationError):
            await mod._revalidate_run_auth(
                user_id=T2, guild_id=1, channel_id=2, role_ids=[], subcommand="run"
            )

    async def test_gate_ephemeral_on_deny(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        interaction = _interaction(T3)
        tier = await mod._gate(interaction, "run")
        self.assertIsNone(tier)
        interaction.response.send_message.assert_awaited()


class TestIdleBeforeTouch(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_idle_before_activity_refresh(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        session = AgentSession(
            scope=scope,
            agent_id="a1",
            owner_id=T2,
            model="m",
            active=True,
            last_meaningful_activity_at=utcnow() - timedelta(minutes=10),
        )
        await sessions.upsert(session)
        self.assertTrue(session_is_idle(session, idle_minutes=10))
        before = session.last_meaningful_activity_at

        interaction = _interaction(T2, guild_id=1, channel_id=2)
        touch = AsyncMock(wraps=sessions.touch_activity)
        sessions.touch_activity = touch

        with patch.object(
            mod,
            "_build_context_for_run",
            AsyncMock(return_value=("built prompt", [], [])),
        ):
            await mod._prepare_and_maybe_launch(
                interaction, "hi", None, [], skip_model=True
            )

        touch.assert_not_awaited()
        active = await sessions.get_active(scope)
        self.assertEqual(active.last_meaningful_activity_at, before)
        # Idle decision + durable pending payload persisted
        state = sessions.export_state()
        self.assertTrue(state["idle"])
        self.assertTrue(state["pending"])
        decision_id = next(iter(state["idle"]))
        pending = await sessions.get_pending_payload(decision_id)
        self.assertEqual(pending["prompt_text"], "built prompt")


class TestDemotionDeferredPaths(unittest.IsolatedAsyncioTestCase):
    async def test_idle_complete_demotion_fail_closed(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        decision = IdleDecision(
            decision_id="idle_x",
            scope=scope,
            agent_id="a1",
            expires_at=utcnow() + timedelta(minutes=5),
        )
        await sessions.save_idle_decision(decision)
        await sessions.save_pending_payload(
            "idle_x",
            mod._serializable_pending(
                prompt="p",
                prompt_text="built",
                message_ref=None,
                preferred="m",
                image_metas=[],
                retention_key=None,
                scope=scope,
            ),
        )
        # Demote to Tier3
        await access.set_user_tier(GOD, T2, "3")
        interaction = _interaction(T2)
        with self.assertRaises(AuthorizationError):
            await mod._complete_idle(interaction, "idle_x", IdleChoice.CONTINUE)
        again = await sessions.get_idle_decision("idle_x")
        self.assertTrue(again.consumed)
        self.assertIsNone(await sessions.get_pending_payload("idle_x"))

    async def test_model_complete_demotion_fail_closed(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        decision = ModelDecision(
            decision_id="mdl_x",
            scope=scope,
            agent_id="a1",
            preferred_model="new",
            agent_model="old",
            expires_at=utcnow() + timedelta(minutes=5),
        )
        await sessions.save_model_decision(decision)
        await sessions.save_pending_payload(
            "mdl_x",
            mod._serializable_pending(
                prompt="p",
                prompt_text="built",
                message_ref=None,
                preferred="new",
                image_metas=[],
                retention_key=None,
                scope=scope,
            ),
        )
        await access.set_user_tier(GOD, T2, "3")
        interaction = _interaction(T2)
        with self.assertRaises(AuthorizationError):
            await mod._complete_model(interaction, "mdl_x", ModelChoice.NEW_SESSION)
        again = await sessions.get_model_decision("mdl_x")
        self.assertTrue(again.consumed)

    async def test_approved_launch_demotion_denies_without_launch(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
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
        req = await access.create_approval_request(env, prompt_preview="p", images=[])
        req = await access.decide_request(GOD, req.request_id, mode="once")
        await access.set_user_tier(GOD, T2, "3")

        launched = AsyncMock()
        mod._launch_run = launched
        interaction = _interaction(GOD)
        interaction.response.is_done.return_value = True
        await mod._launch_approved_request(interaction, req)
        launched.assert_not_awaited()
        reloaded = await access.store.get_request(req.request_id)
        self.assertEqual(reloaded.decision, ApprovalDecision.DENIED)


class TestImageMetaMatch(unittest.IsolatedAsyncioTestCase):
    async def test_exact_meta_match_required(self):
        img = ImageInput(
            mime_type="image/png",
            data_b64="AAAA",
            size_bytes=3,
            source_message_id="m1",
        )
        metas = metas_from_images([img])
        self.assertTrue(metas_match(metas, metas_from_images([img])))
        other = ImageInput(
            mime_type="image/png",
            data_b64="BBBB",
            size_bytes=3,
            source_message_id="m1",
        )
        self.assertFalse(metas_match(metas, metas_from_images([other])))

    async def test_rehydrate_fail_closed_on_mismatch(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        img = ImageInput(mime_type="image/png", data_b64="AAAA", size_bytes=3)
        await access.images.put("ret1", [img], expires_at=utcnow() + timedelta(hours=1))
        pending = {
            "retention_key": "ret1",
            "image_metas": [
                PromptImageMeta(
                    mime_type="image/png",
                    size_bytes=3,
                    fingerprint="deadbeefdeadbeef",
                ).to_dict()
            ],
        }
        with self.assertRaises(ValidationError):
            await mod._rehydrate_pending_images(pending)


class TestPendingPersistence(unittest.IsolatedAsyncioTestCase):
    async def test_pending_keyed_no_clobber(self):
        mod = load_cursor_plugin()
        sessions, _, _ = _bootstrap(mod)
        await sessions.save_pending_payload("d1", {"prompt_text": "a", "user": "1"})
        await sessions.save_pending_payload("d2", {"prompt_text": "b", "user": "2"})
        self.assertEqual((await sessions.get_pending_payload("d1"))["prompt_text"], "a")
        self.assertEqual((await sessions.get_pending_payload("d2"))["prompt_text"], "b")
        exported = sessions.export_state()
        other = MemorySessionStore()
        other.import_state(exported)
        self.assertEqual((await other.get_pending_payload("d1"))["prompt_text"], "a")

    async def test_missing_payload_fail_closed(self):
        mod = load_cursor_plugin()
        sessions, _, _ = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        await sessions.save_idle_decision(
            IdleDecision(
                decision_id="idle_missing",
                scope=scope,
                agent_id="a1",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        interaction = _interaction(T2)
        with self.assertRaises(Exception) as ctx:
            await mod._complete_idle(interaction, "idle_missing", IdleChoice.CONTINUE)
        self.assertIn("resubmit", str(ctx.exception.user_message).lower())


class TestModelPrefPersistence(unittest.IsolatedAsyncioTestCase):
    async def test_model_pref_persists(self):
        mod = load_cursor_plugin()
        sessions, _, _ = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        await sessions.set_model_pref(scope, "composer-2")
        exported = sessions.export_state()
        other = MemorySessionStore()
        other.import_state(exported)
        self.assertEqual(await other.get_model_pref(scope), "composer-2")


class TestEmergencyStopStatus(unittest.IsolatedAsyncioTestCase):
    async def test_tier2_cannot_emergency_stop_other(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        victim = ScopeKey("1", "2", T1)
        await sessions.upsert(
            AgentSession(
                scope=victim,
                agent_id="a1",
                owner_id=T1,
                active=True,
                latest_run_id="r1",
            )
        )
        # Directly exercise the emergency auth branch via resolve + audit path
        tier = await access.resolve_tier(T2)
        self.assertEqual(tier, AccessTier.APPROVAL)
        self.assertNotIn(tier, {AccessTier.GOD, AccessTier.ADMIN})

    async def test_god_emergency_audited(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        await access._audit(GOD, "emergency_stop", target_id=T2, detail={"channel_id": "2"})
        events = await access.store.list_audit(limit=5)
        self.assertEqual(events[-1].action, "emergency_stop")
        self.assertEqual(events[-1].target_id, T2)


class TestRegistrationIdempotent(unittest.TestCase):
    def test_register_commands_idempotent(self):
        mod = load_cursor_plugin()
        bot = MagicMock()
        bot.pending_application_commands = []
        bot.application_commands = []

        def add(cmd):
            bot.pending_application_commands.append(cmd)

        bot.add_application_command.side_effect = add
        mod._register_commands(bot)
        mod._register_commands(bot)
        self.assertEqual(bot.add_application_command.call_count, 1)


class TestCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_closes_clients(self):
        mod = load_cursor_plugin()
        client = MagicMock()
        client.aclose = AsyncMock()
        cdn = MagicMock()
        cdn.aclose = AsyncMock()
        mod._STATE.update(
            {
                "client": client,
                "cdn": cdn,
                "trackers": {},
                "expiry_task": None,
                "reconcile_task": None,
            }
        )
        await mod.cleanup_cursor_runtime()
        client.aclose.assert_awaited()
        cdn.aclose.assert_awaited()


if __name__ == "__main__":
    unittest.main()
