import pathlib
import sys
import unittest
from datetime import timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.errors import OwnershipError
from cursor_cloud.models import AgentSession, IdleChoice, RunStatus, ScopeKey, utcnow
from cursor_cloud.session_store import (
    MemorySessionStore,
    is_meaningful_stream_event,
    run_is_busy,
    session_is_idle,
)


class TestSessions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = MemorySessionStore(max_recent=3)
        self.scope = ScopeKey("g", "c", "u1")
        self.other = ScopeKey("g", "c", "u2")
        self.thread = ScopeKey("g", "thread", "u1")

    async def test_scope_isolation_and_ownership(self):
        s1 = AgentSession(scope=self.scope, agent_id="a1", owner_id="u1", active=True)
        await self.store.upsert(s1)
        s2 = AgentSession(scope=self.other, agent_id="a2", owner_id="u2", active=True)
        await self.store.upsert(s2)
        s3 = AgentSession(scope=self.thread, agent_id="a3", owner_id="u1", active=True)
        await self.store.upsert(s3)

        active = await self.store.get_active(self.scope)
        self.assertEqual(active.agent_id, "a1")
        listed = await self.store.list_sessions(self.scope)
        self.assertEqual([x.agent_id for x in listed], ["a1"])
        # Other user's agent is not in this scope bucket.
        self.assertIsNone(await self.store.get_session(self.scope, "a2"))
        foreign = AgentSession(scope=self.scope, agent_id="a9", owner_id="u2")
        await self.store.upsert(foreign)
        with self.assertRaises(OwnershipError):
            await self.store.get_session(self.scope, "a9")

    async def test_model_preference_and_switch(self):
        await self.store.upsert(
            AgentSession(scope=self.scope, agent_id="a1", owner_id="u1", active=True)
        )
        await self.store.upsert(
            AgentSession(scope=self.scope, agent_id="a2", owner_id="u1")
        )
        await self.store.set_active(self.scope, "a2")
        active = await self.store.get_active(self.scope)
        self.assertEqual(active.agent_id, "a2")
        active.preferred_model = "composer-2"
        await self.store.upsert(active)
        again = await self.store.get_active(self.scope)
        self.assertEqual(again.preferred_model, "composer-2")

    async def test_beacon_roundtrip_export_import(self):
        await self.store.upsert(
            AgentSession(
                scope=self.scope,
                agent_id="a1",
                owner_id="u1",
                active=True,
                summary="hi",
            )
        )
        data = self.store.export_state()
        other = MemorySessionStore()
        other.import_state(data)
        active = await other.get_active(self.scope)
        self.assertEqual(active.agent_id, "a1")
        self.assertEqual(active.summary, "hi")

    async def test_import_state_migrates_legacy_idle_model_buckets(self):
        """Legacy Beacon export_state with idle/model buckets loads into decisions."""
        scope = self.scope.to_dict()
        legacy = {
            "sessions": {},
            "active": {},
            "idle": {
                "idle_legacy": {
                    "decision_id": "idle_legacy",
                    "scope": scope,
                    "agent_id": "a1",
                    "choice": IdleChoice.PENDING.value,
                    "created_at": utcnow().isoformat().replace("+00:00", "Z"),
                    "expires_at": None,
                    "consumed": False,
                    "message_channel_id": "c1",
                    "message_id": "m1",
                }
            },
            "model": {
                "mdl_legacy": {
                    "decision_id": "mdl_legacy",
                    "scope": scope,
                    "agent_id": "a1",
                    "preferred_model": "new-model",
                    "agent_model": "old-model",
                    "choice": IdleChoice.PENDING.value,
                    "created_at": utcnow().isoformat().replace("+00:00", "Z"),
                    "expires_at": None,
                    "consumed": False,
                    "message_channel_id": None,
                    "message_id": None,
                }
            },
            "pending": {
                "idle_legacy": {"prompt_text": "keep me"},
            },
            "model_prefs": {},
        }
        other = MemorySessionStore()
        other.import_state(legacy)

        idle = await other.get_decision("idle_legacy")
        self.assertIsNotNone(idle)
        self.assertEqual(idle.kind, "idle")
        self.assertEqual(idle.agent_id, "a1")
        self.assertEqual(idle.message_channel_id, "c1")
        self.assertFalse(idle.consumed)

        model = await other.get_decision("mdl_legacy")
        self.assertIsNotNone(model)
        self.assertEqual(model.kind, "model")
        self.assertEqual(model.extras.get("preferred_model"), "new-model")
        self.assertEqual(model.extras.get("agent_model"), "old-model")

        open_idle = await other.find_open_decision(self.scope, "idle")
        self.assertEqual(open_idle.decision_id, "idle_legacy")
        open_model = await other.find_open_decision(self.scope, "model")
        self.assertEqual(open_model.decision_id, "mdl_legacy")

        pending = await other.get_pending_payload("idle_legacy")
        self.assertEqual(pending["prompt_text"], "keep me")

        # Re-export uses unified decisions bucket (no legacy idle/model keys).
        exported = other.export_state()
        self.assertIn("decisions", exported)
        self.assertNotIn("idle", exported)
        self.assertNotIn("model", exported)
        self.assertEqual(exported["decisions"]["idle_legacy"]["kind"], "idle")
        self.assertEqual(exported["decisions"]["mdl_legacy"]["kind"], "model")

    async def test_bounded_history(self):
        for i in range(5):
            await self.store.upsert(
                AgentSession(scope=self.scope, agent_id=f"a{i}", owner_id="u1")
            )
        items = await self.store.list_sessions(self.scope)
        self.assertEqual(len(items), 3)

    async def test_idle_boundary_and_meaningful_events(self):
        session = AgentSession(scope=self.scope, agent_id="a1", owner_id="u1")
        session.last_meaningful_activity_at = utcnow() - timedelta(minutes=10)
        self.assertTrue(session_is_idle(session, idle_minutes=10))
        session.last_meaningful_activity_at = utcnow() - timedelta(minutes=9, seconds=50)
        self.assertFalse(session_is_idle(session, idle_minutes=10))
        self.assertTrue(is_meaningful_stream_event("assistant"))
        self.assertTrue(is_meaningful_stream_event("tool_call"))
        self.assertFalse(is_meaningful_stream_event("heartbeat"))
        self.assertFalse(is_meaningful_stream_event("interaction_update"))

    async def test_busy_statuses(self):
        self.assertTrue(run_is_busy(RunStatus.RUNNING))
        self.assertTrue(run_is_busy("CREATING"))
        self.assertFalse(run_is_busy(RunStatus.FINISHED))


if __name__ == "__main__":
    unittest.main()
