"""Thread-session UX tests for SONA-105 (/cursor new + bound threads)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.access import AccessController, ImageRetentionStore, MemoryAccessStore
from cursor_cloud.config import load_cursor_config
from cursor_cloud.models import (
    AgentSession,
    RunSnapshot,
    RunStatus,
    ScopeKey,
    ToolActivity,
    utcnow,
)
from cursor_cloud.session_store import MemorySessionStore
from cursor_cloud.thread_renderer import render_thread_activity, render_thread_final
from cursor_cloud.thread_session import (
    owner_reply_to_human,
    policy_channel_id,
    thread_session_immutable_violation,
)
from cursor_cloud.thread_sink import ThreadActivitySink


GOD = "100000000000000001"
T2 = "100000000000000003"
OWNER = T2
OTHER = "100000000000000011"


def load_cursor_plugin():
    from modules.AI_manager import AI_Manager

    path = ROOT / "src" / "modules" / "plugins" / "cursor-commands.py"
    spec = importlib.util.spec_from_file_location("cursor_commands_thread", path)
    module = importlib.util.module_from_spec(spec)
    previous = AI_Manager.M.MANAGER
    try:
        spec.loader.exec_module(module)
    finally:
        AI_Manager.M.MANAGER = previous
    return module


class ParentAllowsChildDeniesPolicy:
    def can_speak(self, *, guild_id, channel_id, user_id, role_ids):
        return str(channel_id) == "100"

    def is_command_allowed(self, *, guild_id, channel_id, command, user_id, role_ids):
        return str(channel_id) == "100"


class TestThreadSessionHelpers(unittest.TestCase):
    def test_policy_inherits_parent_channel(self):
        session = AgentSession(
            scope=ScopeKey("1", "200", OWNER),
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
        )
        self.assertEqual(
            policy_channel_id(channel_id="200", session=session),
            "100",
        )

    def test_immutability_violation(self):
        session = AgentSession(
            scope=ScopeKey("1", "200", OWNER),
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
        )
        self.assertTrue(
            thread_session_immutable_violation(
                session, force_new=True, agent_id=None
            )
        )
        self.assertTrue(
            thread_session_immutable_violation(
                session, force_new=False, agent_id="bc-other"
            )
        )
        self.assertFalse(
            thread_session_immutable_violation(
                session, force_new=False, agent_id="bc-1"
            )
        )

    def test_owner_reply_to_human(self):
        human = SimpleNamespace(id=int(OTHER), bot=False)
        owner = SimpleNamespace(id=int(OWNER), bot=False)
        bot = SimpleNamespace(id=999, bot=True)
        ref_human = SimpleNamespace(message_id=1, resolved=SimpleNamespace(author=human))
        ref_bot = SimpleNamespace(message_id=2, resolved=SimpleNamespace(author=bot))
        ref_self = SimpleNamespace(message_id=3, resolved=SimpleNamespace(author=owner))
        msg_to_human = SimpleNamespace(reference=ref_human)
        msg_to_bot = SimpleNamespace(reference=ref_bot)
        msg_to_self = SimpleNamespace(reference=ref_self)
        msg_plain = SimpleNamespace(reference=None)
        self.assertTrue(owner_reply_to_human(msg_to_human, OWNER))
        self.assertFalse(owner_reply_to_human(msg_to_bot, OWNER))
        self.assertFalse(owner_reply_to_human(msg_to_self, OWNER))
        self.assertFalse(owner_reply_to_human(msg_plain, OWNER))


class TestThreadRenderer(unittest.TestCase):
    def test_activity_coalesces_tool_families(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.RUNNING,
            tools=[
                ToolActivity("1", "grep", "running", "keys=pattern"),
                ToolActivity("2", "grep", "completed", "keys=pattern2"),
                ToolActivity("3", "Task", "running", "subagent"),
            ],
        )
        text = render_thread_activity(snap)
        self.assertIn("search", text)
        self.assertIn("×2", text)
        self.assertLessEqual(len(text), 2000)

    def test_final_is_separate_body(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="hello @everyone",
        )
        final = render_thread_final(snap)
        self.assertIn("### Result", final)
        self.assertNotIn("@everyone", final)


class TestThreadActivitySink(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_posts_final_once(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        sink = ThreadActivitySink(channel, activity, edit_interval_ms=0)
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="done",
        )
        await sink.update_from_snapshot(snap, terminal=True)
        await sink.update_from_snapshot(snap, terminal=True)
        self.assertEqual(channel.send.await_count, 1)
        self.assertGreaterEqual(activity.edit.await_count, 1)


class TestFindThreadSession(unittest.IsolatedAsyncioTestCase):
    async def test_find_thread_session_by_thread_id(self):
        store = MemorySessionStore()
        session = AgentSession(
            scope=ScopeKey("1", "thread-9", OWNER),
            agent_id="bc-9",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            active=True,
        )
        await store.upsert(session)
        found = await store.find_thread_session("thread-9")
        self.assertIsNotNone(found)
        self.assertEqual(found.agent_id, "bc-9")


class TestThreadMessageRouting(unittest.IsolatedAsyncioTestCase):
    async def test_owner_plain_message_triggers_prepare(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        access = AccessController(
            cfg, MemoryAccessStore(), image_retention=ImageRetentionStore(max_total_bytes=1)
        )
        mod._STATE.update(
            {
                "config": cfg,
                "sessions": sessions,
                "access": access,
                "policy_manager": ParentAllowsChildDeniesPolicy(),
                "require_policy": True,
                "handled_thread_messages": set(),
                "bot": MagicMock(),
            }
        )
        session = AgentSession(
            scope=ScopeKey("1", "200", OWNER),
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="555",
            latest_run_status=RunStatus.FINISHED,
            active=True,
        )
        await sessions.upsert(session)

        owner = SimpleNamespace(id=int(OWNER), bot=False, roles=[])
        activity = MagicMock()
        activity.id = 555
        thread = MagicMock()
        thread.id = 200
        thread.parent_id = 100
        thread.archived = False
        thread.edit = AsyncMock()
        thread.fetch_message = AsyncMock(return_value=activity)
        thread.send = AsyncMock(return_value=activity)

        message = SimpleNamespace(
            id=1001,
            author=owner,
            content="follow up please",
            attachments=[],
            reference=None,
            channel=thread,
            guild=SimpleNamespace(id=1),
        )

        with patch.object(mod, "_prepare_and_maybe_launch", new=AsyncMock()) as launch:
            handled = await mod.handle_thread_message(message)
        self.assertTrue(handled)
        launch.assert_awaited_once()

    async def test_non_owner_and_human_reply_ignored(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {"enabled": True, "default_repository_url": "https://github.com/o/r"},
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        mod._STATE.update(
            {
                "config": cfg,
                "sessions": sessions,
                "access": AccessController(cfg, MemoryAccessStore()),
                "policy_manager": ParentAllowsChildDeniesPolicy(),
                "handled_thread_messages": set(),
            }
        )
        session = AgentSession(
            scope=ScopeKey("1", "200", OWNER),
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            active=True,
        )
        await sessions.upsert(session)

        thread = MagicMock()
        thread.id = 200
        thread.parent_id = 100
        other = SimpleNamespace(id=int(OTHER), bot=False, roles=[])
        human = SimpleNamespace(id=int(OTHER), bot=False)
        ref = SimpleNamespace(
            message_id=1,
            resolved=SimpleNamespace(author=human),
        )
        msg_other = SimpleNamespace(
            id=2001,
            author=other,
            content="hello",
            attachments=[],
            reference=None,
            channel=thread,
            guild=SimpleNamespace(id=1),
        )
        msg_owner_reply = SimpleNamespace(
            id=2002,
            author=SimpleNamespace(id=int(OWNER), bot=False, roles=[]),
            content="thanks",
            attachments=[],
            reference=ref,
            channel=thread,
            guild=SimpleNamespace(id=1),
        )
        with patch.object(mod, "_prepare_and_maybe_launch", new=AsyncMock()) as launch:
            self.assertTrue(await mod.handle_thread_message(msg_other))
            self.assertTrue(await mod.handle_thread_message(msg_owner_reply))
        launch.assert_not_awaited()

    async def test_bot_messages_ignored(self):
        mod = load_cursor_plugin()
        sessions = MemorySessionStore()
        mod._STATE.update({"sessions": sessions, "handled_thread_messages": set()})
        thread = MagicMock()
        thread.id = 200
        thread.parent_id = 100
        bot_user = SimpleNamespace(id=999, bot=True, roles=[])
        message = SimpleNamespace(
            id=3001,
            author=bot_user,
            content="beep",
            attachments=[],
            reference=None,
            channel=thread,
            guild=None,
        )
        self.assertFalse(await mod.handle_thread_message(message))


class TestParentPolicyInheritance(unittest.IsolatedAsyncioTestCase):
    async def test_thread_scope_uses_parent_policy_channel(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        mod._STATE.update(
            {
                "config": cfg,
                "access": AccessController(cfg, MemoryAccessStore()),
                "policy_manager": ParentAllowsChildDeniesPolicy(),
                "require_policy": True,
            }
        )
        tier = await mod._revalidate_run_auth(
            user_id=T2,
            guild_id=1,
            channel_id=200,
            role_ids=[],
            subcommand="run",
            policy_channel_id="100",
        )
        self.assertIsNotNone(tier)
        with self.assertRaises(Exception):
            await mod._revalidate_run_auth(
                user_id=T2,
                guild_id=1,
                channel_id=200,
                role_ids=[],
                subcommand="run",
                policy_channel_id="999",
            )


if __name__ == "__main__":
    unittest.main()
