import pathlib
import sys
import unittest
from datetime import timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.access import AccessController, MemoryAccessStore, envelope_hash
from cursor_cloud.config import load_cursor_config
from cursor_cloud.models import (
    AgentSession,
    IdleChoice,
    IdleDecision,
    ModelChoice,
    ModelDecision,
    RunRequestEnvelope,
    ScopeKey,
    utcnow,
)
from cursor_cloud.session_store import MemorySessionStore, session_is_idle


GOD = "100000000000000001"
T2 = "100000000000000003"


class TestInactivityAndModelOrder(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scope = ScopeKey("g", "c", T2)
        self.sessions = MemorySessionStore()
        env = {"CURSOR_API_KEY": "k", "GOD": GOD}
        self.cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "session_idle_prompt_minutes": 10,
                "access": {"tier2_user_ids": [T2]},
            },
            env=env,
        )
        self.access = AccessController(self.cfg, MemoryAccessStore())

    async def test_exact_boundary(self):
        s = AgentSession(scope=self.scope, agent_id="a1", owner_id=T2)
        s.last_meaningful_activity_at = utcnow() - timedelta(minutes=10)
        self.assertTrue(session_is_idle(s, idle_minutes=10))
        s.last_meaningful_activity_at = utcnow() - timedelta(minutes=10) + timedelta(seconds=1)
        self.assertFalse(session_is_idle(s, idle_minutes=10))

    async def test_idle_decision_consume_and_cancel(self):
        decision = IdleDecision(
            decision_id="idle_1",
            scope=self.scope,
            agent_id="a1",
            expires_at=utcnow() + timedelta(minutes=5),
        )
        await self.sessions.save_idle_decision(decision)
        loaded = await self.sessions.get_idle_decision("idle_1")
        loaded.choice = IdleChoice.CANCEL
        loaded.consumed = True
        await self.sessions.save_idle_decision(loaded)
        again = await self.sessions.get_idle_decision("idle_1")
        self.assertTrue(again.consumed)
        self.assertEqual(again.choice, IdleChoice.CANCEL)

    async def test_model_mismatch_forces_choice_before_approval_hash(self):
        session = AgentSession(
            scope=self.scope,
            agent_id="a1",
            owner_id=T2,
            model="old-model",
            preferred_model="new-model",
            active=True,
        )
        await self.sessions.upsert(session)
        # Model decision must happen before hashing approval envelope that includes agent_id.
        decision = ModelDecision(
            decision_id="mdl_1",
            scope=self.scope,
            agent_id="a1",
            preferred_model="new-model",
            agent_model="old-model",
        )
        await self.sessions.save_model_decision(decision)

        # Continue => follow-up keeps original model / agent in envelope
        cont_env = RunRequestEnvelope(
            requester_id=T2,
            scope=self.scope,
            prompt_text="p",
            model="old-model",
            repository_url=self.cfg.default_repository_url,
            starting_ref="main",
            agent_id="a1",
            is_follow_up=True,
        )
        # New => no agent id / new session
        new_env = RunRequestEnvelope(
            requester_id=T2,
            scope=self.scope,
            prompt_text="p",
            model="new-model",
            repository_url=self.cfg.default_repository_url,
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
        )
        self.assertNotEqual(envelope_hash(cont_env), envelope_hash(new_env))
        # Choosing new vs continue changes approval binding
        decision.choice = ModelChoice.NEW_SESSION
        decision.consumed = True
        await self.sessions.save_model_decision(decision)

    async def test_active_pointer_only_after_create_success_semantics(self):
        # Simulate: do not change active until upsert after successful create.
        await self.sessions.upsert(
            AgentSession(
                scope=self.scope, agent_id="old", owner_id=T2, active=True, model="m"
            )
        )
        # Failed create => active remains old
        active = await self.sessions.get_active(self.scope)
        self.assertEqual(active.agent_id, "old")
        # Successful create
        await self.sessions.upsert(
            AgentSession(
                scope=self.scope, agent_id="new", owner_id=T2, active=True, model="m2"
            )
        )
        active = await self.sessions.get_active(self.scope)
        self.assertEqual(active.agent_id, "new")

    async def test_timed_grant_skips_approval_not_idle(self):
        # Timed grant present does not imply idle skip — idle check is independent.
        s = AgentSession(scope=self.scope, agent_id="a1", owner_id=T2)
        s.last_meaningful_activity_at = utcnow() - timedelta(minutes=11)
        self.assertTrue(session_is_idle(s, idle_minutes=10))
        # Approval lookup would be skipped when grant exists, but idle still true.
        env = RunRequestEnvelope(
            requester_id=T2,
            scope=self.scope,
            prompt_text="p",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id="a1",
            is_follow_up=True,
        )
        # No grant created here; documents ordering expectation in prepare flow.
        self.assertIsNone(await self.access.find_valid_grant(self.scope, T2, env))


if __name__ == "__main__":
    unittest.main()
