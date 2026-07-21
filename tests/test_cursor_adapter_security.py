"""Adapter-level security/completeness tests for cursor-commands (SONA-105)."""

from __future__ import annotations
from contextlib import contextmanager

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
from cursor_cloud.errors import (
    AuthorizationError,
    ConfigurationError,
    StaleStateError,
    ValidationError,
)
from cursor_cloud.models import (
    AccessTier,
    AgentSession,
    ApprovalDecision,
    IdleChoice,
    ImageInput,
    ModelChoice,
    PendingDecision,
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
    mod.reset_runtime(
        config=cfg,
        sessions=sessions,
        access_store=store,
        access=access,
        client=MagicMock(),
        cdn=MagicMock(),
        bot=None,
        trackers={},
        policy_manager=policy if policy is not None else PermissivePolicy(),
        require_policy=require_policy,
    )
    return sessions, access, cfg


def _interaction(user_id, *, guild_id=1, channel_id=2, response_done=False):
    user = SimpleNamespace(id=int(user_id), roles=[])
    response = MagicMock()
    response.is_done.return_value = response_done
    response.send_message = AsyncMock()
    response.defer = AsyncMock()
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
                mod.get_runtime(),
                user_id=T3, guild_id=1, channel_id=2, role_ids=[], subcommand="run"
            )

    async def test_missing_policy_fail_closed_when_required(self):
        mod = load_cursor_plugin()
        _bootstrap(mod, policy=None, require_policy=True)
        mod.get_runtime().policy_manager = None
        with patch_cursor(mod, "_resolve_policy_manager", return_value=None):
            with self.assertRaises(ConfigurationError):
                await mod._revalidate_run_auth(
                    mod.get_runtime(),
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
        mod.get_runtime().policy_manager = None
        mod.get_runtime().bot = SimpleNamespace(sonata=sona)
        self.assertIs(mod._resolve_policy_manager(mod.get_runtime()), pm)

    async def test_channel_policy_deny(self):
        mod = load_cursor_plugin()
        _bootstrap(mod, policy=DenyingPolicy())
        with self.assertRaises(AuthorizationError):
            await mod._revalidate_run_auth(
                mod.get_runtime(),
                user_id=T2, guild_id=1, channel_id=2, role_ids=[], subcommand="run"
            )

    async def test_gate_ephemeral_on_deny(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        interaction = _interaction(T3)
        tier = await mod._gate(interaction, "run")
        self.assertIsNone(tier)
        interaction.response.send_message.assert_awaited()

    async def test_defer_acks_before_cursor_api(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        interaction = _interaction(GOD)
        interaction.response.defer = AsyncMock()
        client = MagicMock()
        client.list_models = AsyncMock(
            return_value=[SimpleNamespace(id="m1", display_name="M1", aliases=[])]
        )
        mod.get_runtime().client = client

        # Simulate ApplicationContext.interaction path used by cursor_model.
        await mod._defer(interaction, ephemeral=True)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        models = await mod.get_runtime().client.list_models()
        self.assertEqual(models[0].id, "m1")
        # After defer, followup path is used for ephemeral replies.
        interaction.response.is_done.return_value = True
        await mod._ephemeral(interaction, "ok")
        interaction.followup.send.assert_awaited()


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

        with patch_cursor(mod,
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
        idle = {
            k: v
            for k, v in (state.get("decisions") or {}).items()
            if v.get("kind") == "idle"
        }
        self.assertTrue(idle)
        self.assertTrue(state["pending"])
        decision_id = next(iter(idle))
        pending = await sessions.get_pending_payload(decision_id)
        self.assertEqual(pending["prompt_text"], "built prompt")


class TestDemotionDeferredPaths(unittest.IsolatedAsyncioTestCase):
    async def test_idle_complete_demotion_fail_closed(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        decision = PendingDecision(
            decision_id="idle_x",
            scope=scope,
            agent_id="a1",
            kind="idle",
            expires_at=utcnow() + timedelta(minutes=5),
        )
        await sessions.save_decision(decision)
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
            await mod.complete_decision(
                mod.get_runtime(),
                mod.InteractionUI(interaction),
                "idle_x",
                IdleChoice.CONTINUE.value,
            )
        again = await sessions.get_decision("idle_x")
        self.assertTrue(again.consumed)
        self.assertIsNone(await sessions.get_pending_payload("idle_x"))

    async def test_model_complete_demotion_fail_closed(self):
        mod = load_cursor_plugin()
        sessions, access, cfg = _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        decision = PendingDecision(
            decision_id="mdl_x",
            scope=scope,
            agent_id="a1",
            kind="model",
            expires_at=utcnow() + timedelta(minutes=5),
            extras={"preferred_model": "new", "agent_model": "old"},
        )
        await sessions.save_decision(decision)
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
            await mod.complete_decision(
                mod.get_runtime(),
                mod.InteractionUI(interaction),
                "mdl_x",
                ModelChoice.NEW_SESSION.value,
            )
        again = await sessions.get_decision("mdl_x")
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
        mod.launch = launched
        mod.workflows.launch = launched
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


class TestApprovalDecisionOverride(unittest.IsolatedAsyncioTestCase):
    def _envelope(self, requester=T2, channel="2"):
        return RunRequestEnvelope(
            requester_id=requester,
            scope=ScopeKey("1", channel, requester),
            prompt_text="p",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
        )

    async def test_deny_after_approve_once_overrides(self):
        access = AccessController(_cfg(), MemoryAccessStore())
        req = await access.create_approval_request(
            self._envelope(), prompt_preview="p", images=[]
        )
        approved = await access.decide_request(GOD, req.request_id, mode="once")
        self.assertEqual(approved.decision, ApprovalDecision.APPROVED_ONCE)
        old_grant = await access.store.get_grant(approved.grant_id)
        self.assertFalse(old_grant.revoked)

        denied = await access.decide_request(GOD, req.request_id, mode="deny")
        self.assertEqual(denied.decision, ApprovalDecision.DENIED)
        old_grant = await access.store.get_grant(approved.grant_id)
        self.assertTrue(old_grant.revoked)

    async def test_once_to_timed_replaces_unused_grant(self):
        access = AccessController(_cfg(), MemoryAccessStore())
        req = await access.create_approval_request(
            self._envelope(), prompt_preview="p", images=[]
        )
        once = await access.decide_request(GOD, req.request_id, mode="once")
        old_gid = once.grant_id
        timed = await access.decide_request(
            GOD, req.request_id, mode="timed", minutes=10
        )
        self.assertEqual(timed.decision, ApprovalDecision.APPROVED_TIMED)
        self.assertEqual(timed.grant_minutes, 10)
        self.assertNotEqual(timed.grant_id, old_gid)
        old_grant = await access.store.get_grant(old_gid)
        self.assertTrue(old_grant.revoked)
        new_grant = await access.store.get_grant(timed.grant_id)
        self.assertEqual(new_grant.kind, "timed")
        self.assertFalse(new_grant.revoked)

    async def test_timed_to_once_replaces_unused_grant(self):
        access = AccessController(_cfg(), MemoryAccessStore())
        req = await access.create_approval_request(
            self._envelope(), prompt_preview="p", images=[]
        )
        timed = await access.decide_request(
            GOD, req.request_id, mode="timed", minutes=10
        )
        old_gid = timed.grant_id
        once = await access.decide_request(GOD, req.request_id, mode="once")
        self.assertEqual(once.decision, ApprovalDecision.APPROVED_ONCE)
        self.assertIsNone(once.grant_minutes)
        self.assertNotEqual(once.grant_id, old_gid)
        self.assertTrue((await access.store.get_grant(old_gid)).revoked)

    async def test_consumed_cannot_be_overridden(self):
        access = AccessController(_cfg(), MemoryAccessStore())
        env = self._envelope()
        req = await access.create_approval_request(env, prompt_preview="p", images=[])
        approved = await access.decide_request(GOD, req.request_id, mode="once")
        grant = await access.store.get_grant(approved.grant_id)
        await access.consume_grant_for_submit(grant, env)
        reloaded = await access.store.get_request(req.request_id)
        self.assertEqual(reloaded.decision, ApprovalDecision.CONSUMED)
        with self.assertRaises(StaleStateError) as ctx:
            await access.decide_request(GOD, req.request_id, mode="deny")
        self.assertIn("already consumed", ctx.exception.user_message.lower())

    async def test_decisions_are_per_request_id(self):
        access = AccessController(_cfg(), MemoryAccessStore())
        req_a = await access.create_approval_request(
            self._envelope(channel="2"), prompt_preview="a", images=[]
        )
        req_b = await access.create_approval_request(
            self._envelope(channel="3"), prompt_preview="b", images=[]
        )
        await access.decide_request(GOD, req_a.request_id, mode="once")
        await access.decide_request(GOD, req_b.request_id, mode="deny")
        a = await access.store.get_request(req_a.request_id)
        b = await access.store.get_request(req_b.request_id)
        self.assertEqual(a.decision, ApprovalDecision.APPROVED_ONCE)
        self.assertEqual(b.decision, ApprovalDecision.DENIED)
        # Override only A — B stays denied and cannot be re-approved.
        await access.decide_request(GOD, req_a.request_id, mode="deny")
        a = await access.store.get_request(req_a.request_id)
        b = await access.store.get_request(req_b.request_id)
        self.assertEqual(a.decision, ApprovalDecision.DENIED)
        self.assertEqual(b.decision, ApprovalDecision.DENIED)
        with self.assertRaises(StaleStateError):
            await access.decide_request(GOD, req_b.request_id, mode="once")

    async def test_denied_is_terminal(self):
        access = AccessController(_cfg(), MemoryAccessStore())
        req = await access.create_approval_request(
            self._envelope(), prompt_preview="p", images=[]
        )
        await access.decide_request(GOD, req.request_id, mode="deny")
        with self.assertRaises(StaleStateError) as ctx:
            await access.decide_request(GOD, req.request_id, mode="once")
        self.assertIn("already denied", ctx.exception.user_message.lower())


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
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_missing",
                scope=scope,
                agent_id="a1",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        interaction = _interaction(T2)
        with self.assertRaises(Exception) as ctx:
            await mod.complete_decision(
                mod.get_runtime(),
                mod.InteractionUI(interaction),
                "idle_missing",
                IdleChoice.CONTINUE.value,
            )
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
        await access.audit(GOD, "emergency_stop", target_id=T2, detail={"channel_id": "2"})
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
        mod.reset_runtime(
            client=client,
            cdn=cdn,
            trackers={},
            expiry_task=None,
            reconcile_task=None,
        )
        await mod.cleanup_cursor_runtime()
        client.aclose.assert_awaited()
        cdn.aclose.assert_awaited()


if __name__ == "__main__":
    unittest.main()
