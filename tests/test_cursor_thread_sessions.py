"""Thread-session UX tests for SONA-105 (/cursor new + bound threads)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

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
from cursor_cloud.thread_renderer import (
    THREAD_THINKING_INDICATOR,
    render_thread_activity,
    render_thread_final,
)
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
        ref_unresolved = SimpleNamespace(message_id=4, resolved=None)
        msg_to_human = SimpleNamespace(reference=ref_human)
        msg_to_bot = SimpleNamespace(reference=ref_bot)
        msg_to_self = SimpleNamespace(reference=ref_self)
        msg_plain = SimpleNamespace(reference=None)
        msg_unresolved = SimpleNamespace(reference=ref_unresolved)
        self.assertTrue(owner_reply_to_human(msg_to_human, OWNER))
        self.assertFalse(owner_reply_to_human(msg_to_bot, OWNER))
        self.assertFalse(owner_reply_to_human(msg_to_self, OWNER))
        self.assertFalse(owner_reply_to_human(msg_plain, OWNER))
        # Unresolved reply references fail closed (skip follow-up).
        self.assertTrue(owner_reply_to_human(msg_unresolved, OWNER))
        self.assertFalse(
            owner_reply_to_human(
                msg_unresolved,
                OWNER,
                resolved_message=SimpleNamespace(author=bot),
            )
        )


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
        self.assertNotIn("Run:", text)
        self.assertNotIn("Agent:", text)
        self.assertLessEqual(len(text), 2000)

    def test_activity_idle_shows_thinking_indicator(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.QUEUED,
        )
        text = render_thread_activity(snap)
        self.assertEqual(text, THREAD_THINKING_INDICATOR)

    def test_final_is_body_only_no_chrome(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="hello @everyone",
            duration_ms=11000,
            git_branches=[],
        )
        from cursor_cloud.models import GitBranchInfo

        snap.git_branches = [
            GitBranchInfo(branch="cursor/demo", pr_url="https://example.com/pr/1")
        ]
        final = render_thread_final(snap)
        self.assertIn("hello", final)
        self.assertNotIn("@everyone", final)
        self.assertNotIn("### Finished", final)
        self.assertNotIn("### Result", final)
        self.assertNotIn("Run:", final)
        self.assertNotIn("### Git", final)
        self.assertNotIn("Duration:", final)


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

    async def test_final_still_posts_when_activity_edit_fails(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock(side_effect=RuntimeError("edit failed"))
        sink = ThreadActivitySink(channel, activity, edit_interval_ms=0)
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="done",
        )
        await sink.update_from_snapshot(snap, terminal=True)
        self.assertEqual(channel.send.await_count, 1)
        self.assertTrue(sink.degraded)


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


class TestApprovalThreadBinding(unittest.IsolatedAsyncioTestCase):
    async def test_approval_request_persists_thread_metadata(self):
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        access = AccessController(
            cfg, MemoryAccessStore(), image_retention=ImageRetentionStore(max_total_bytes=1)
        )
        from cursor_cloud.models import RunRequestEnvelope, ScopeKey as SK

        env = RunRequestEnvelope(
            requester_id=OWNER,
            scope=SK("1", "200", OWNER),
            prompt_text="do the thing",
            model=None,
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
            image_metas=[],
        )
        req = await access.create_approval_request(
            env,
            prompt_preview="do the thing",
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="555",
        )
        loaded = await access.store.get_request(req.request_id)
        self.assertTrue(loaded.thread_bound)
        self.assertEqual(loaded.parent_channel_id, "100")
        self.assertEqual(loaded.status_message_id, "555")
        # Round-trip serialization must keep UX fields (Beacon restart).
        restored = type(loaded).from_dict(loaded.to_dict())
        self.assertTrue(restored.thread_bound)
        self.assertEqual(restored.parent_channel_id, "100")

    async def test_launch_approved_uses_request_thread_binding(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier1_user_ids": [GOD], "tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        store = MemoryAccessStore()
        access = AccessController(
            cfg, store, image_retention=ImageRetentionStore(max_total_bytes=1)
        )
        mod._STATE.update(
            {
                "config": cfg,
                "sessions": sessions,
                "access": access,
                "access_store": store,
                "policy_manager": ParentAllowsChildDeniesPolicy(),
                "require_policy": True,
                "client": MagicMock(),
                "bot": MagicMock(),
            }
        )
        from cursor_cloud.models import (
            ApprovalDecision,
            RunRequestEnvelope,
            ScopeKey as SK,
        )

        env = RunRequestEnvelope(
            requester_id=OWNER,
            scope=SK("1", "200", OWNER),
            prompt_text="do the thing",
            model=None,
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
            image_metas=[],
        )
        req = await access.create_approval_request(
            env,
            prompt_preview="do",
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="555",
        )
        req.decision = ApprovalDecision.APPROVED_ONCE
        await store.save_request(req)

        activity = SimpleNamespace(id=555, channel=SimpleNamespace(id=200))
        channel = MagicMock()
        channel.id = 200
        channel.fetch_message = AsyncMock(return_value=activity)
        channel.send = AsyncMock(return_value=activity)

        interaction = SimpleNamespace(
            user=SimpleNamespace(id=int(GOD), roles=[]),
            guild=SimpleNamespace(
                id=1,
                get_channel=MagicMock(return_value=channel),
            ),
            channel=channel,
            client=SimpleNamespace(fetch_channel=AsyncMock(return_value=channel)),
            message=None,
        )

        access.images.get = AsyncMock(return_value=[])
        access.images.discard = AsyncMock()
        with patch.object(mod, "_launch_run", new=AsyncMock()) as launch:
            with patch.object(mod, "_ephemeral", new=AsyncMock()):
                await mod._launch_approved_request(interaction, req)

        launch.assert_awaited_once()
        kwargs = launch.await_args.kwargs
        self.assertTrue(kwargs["thread_bound"])
        self.assertEqual(kwargs["parent_channel_id"], "100")
        self.assertTrue(kwargs["skip_status_post"])
        self.assertIs(kwargs["status_msg"], activity)


class TestSessionThreadFieldsCompat(unittest.TestCase):
    def test_agent_session_roundtrip_and_legacy(self):
        session = AgentSession(
            scope=ScopeKey("1", "200", OWNER),
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            latest_run_id="run-1",
            latest_git=[{"branch": "cursor/demo", "pr_url": None}],
        )
        restored = AgentSession.from_dict(session.to_dict())
        self.assertTrue(restored.thread_bound)
        self.assertEqual(restored.parent_channel_id, "100")
        self.assertEqual(restored.latest_git[0]["branch"], "cursor/demo")
        legacy = AgentSession.from_dict(
            {
                "scope": {"guild_id": "1", "channel_id": "200", "user_id": OWNER},
                "agent_id": "bc-legacy",
                "owner_id": OWNER,
            }
        )
        self.assertFalse(legacy.thread_bound)
        self.assertIsNone(legacy.parent_channel_id)
        self.assertEqual(legacy.latest_git, [])


class TestSessionTitles(unittest.IsolatedAsyncioTestCase):
    def test_title_from_prompt_slug(self):
        mod = load_cursor_plugin()
        self.assertEqual(
            mod._title_from_prompt("briefly explain how the ispy plugin works"),
            "briefly explain how the ispy plugin works",
        )
        self.assertEqual(
            mod._title_from_prompt("Fix flaky CI. Then deploy."),
            "Fix flaky CI",
        )
        self.assertEqual(mod._sanitize_thread_title('  "Hello\nWorld"  '), "Hello World")

    async def test_start_skips_success_notify_for_starter_message(self):
        mod = load_cursor_plugin()
        notify = AsyncMock()
        thread = SimpleNamespace(
            id=999, mention="<#999>", send=AsyncMock(return_value=SimpleNamespace(id=1, channel=None))
        )
        thread.send.return_value.channel = thread
        starter = MagicMock()
        with patch.object(mod, "_generate_session_title", new=AsyncMock(return_value="ispy overview")):
            with patch.object(
                mod, "_create_public_agent_thread", new=AsyncMock(return_value=thread)
            ):
                with patch.object(
                    mod, "_prepare_and_maybe_launch", new=AsyncMock(return_value="launched")
                ) as prep:
                    await mod._start_thread_bound_session(
                        interaction=SimpleNamespace(),
                        prompt="explain ispy",
                        message_ref=None,
                        images=[],
                        parent_channel=MagicMock(),
                        parent_channel_id="100",
                        user=SimpleNamespace(id=1, name="u", display_name="U"),
                        guild_id=1,
                        starter_message=starter,
                        notify=notify,
                    )
        prep.assert_awaited_once()
        self.assertEqual(prep.await_args.kwargs["agent_display_name"], "ispy overview")
        notify.assert_not_awaited()

    async def test_start_notifies_success_for_slash_new(self):
        mod = load_cursor_plugin()
        notify = AsyncMock()
        thread = SimpleNamespace(
            id=999, mention="<#999>", send=AsyncMock(return_value=SimpleNamespace(id=1))
        )
        thread.send.return_value.channel = thread
        with patch.object(mod, "_generate_session_title", new=AsyncMock(return_value="slash title")):
            with patch.object(
                mod, "_create_public_agent_thread", new=AsyncMock(return_value=thread)
            ):
                with patch.object(
                    mod, "_prepare_and_maybe_launch", new=AsyncMock(return_value="launched")
                ):
                    await mod._start_thread_bound_session(
                        interaction=SimpleNamespace(),
                        prompt="hello",
                        message_ref=None,
                        images=[],
                        parent_channel=MagicMock(),
                        parent_channel_id="100",
                        user=SimpleNamespace(id=1, name="u", display_name="U"),
                        guild_id=1,
                        starter_message=None,
                        notify=notify,
                    )
        notify.assert_awaited_once()
        self.assertIn("Started Cursor session", notify.await_args.args[0])
        self.assertNotIn("auto-archive", notify.await_args.args[0])


class TestThreadFollowupIndicator(unittest.IsolatedAsyncioTestCase):
    async def test_followup_edits_activity_to_thinking_immediately(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier1_user_ids": [GOD], "tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        scope = ScopeKey("1", "200", OWNER)
        session = AgentSession(
            scope=scope,
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="55",
            active=True,
        )
        await sessions.upsert(session)
        await sessions.set_active(scope, "bc-1")
        mod._STATE.update(
            {
                "config": cfg,
                "sessions": sessions,
                "access": AccessController(
                    cfg,
                    MemoryAccessStore(),
                    image_retention=ImageRetentionStore(max_total_bytes=1),
                ),
                "policy_manager": ParentAllowsChildDeniesPolicy(),
                "require_policy": True,
                "bot": MagicMock(),
                "handled_thread_messages": set(),
            }
        )
        activity = MagicMock()
        activity.id = 55
        activity.edit = AsyncMock()
        channel = MagicMock()
        channel.id = 200
        channel.parent_id = 100
        channel.fetch_message = AsyncMock(return_value=activity)
        message = MagicMock()
        message.id = 901
        message.author = SimpleNamespace(id=int(OWNER), bot=False, roles=[])
        message.content = "follow up please"
        message.attachments = []
        message.reference = None
        message.channel = channel
        message.guild = SimpleNamespace(id=1)
        with patch.object(mod, "_channel_is_thread", return_value=True):
            with patch.object(mod, "_revalidate_run_auth", new=AsyncMock()):
                with patch.object(
                    mod,
                    "_build_context_from_message",
                    new=AsyncMock(return_value=("follow up please", [], [])),
                ):
                    with patch.object(
                        mod, "_prepare_and_maybe_launch", new=AsyncMock(return_value="launched")
                    ):
                        ok = await mod.handle_thread_message(message)
        self.assertTrue(ok)
        activity.edit.assert_awaited()
        self.assertEqual(
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0],
            THREAD_THINKING_INDICATOR,
        )


class TestAgentPrefixCommand(unittest.IsolatedAsyncioTestCase):
    async def test_interaction_shim_does_not_patch_channel_send(self):
        """Regression: followup must not alias/overwrite channel.send (RecursionError)."""
        mod = load_cursor_plugin()
        channel = MagicMock()
        channel.id = 100
        channel.send = AsyncMock(return_value=SimpleNamespace(id=1))
        original_send = channel.send
        message = SimpleNamespace(
            id=42,
            author=SimpleNamespace(id=int(T2), roles=[]),
            guild=SimpleNamespace(id=1),
            channel=channel,
        )
        shim = mod._interaction_shim_from_message(message)
        self.assertIs(channel.send, original_send)
        self.assertIsNot(shim.followup, channel)
        await shim.followup.send("hello")
        original_send.assert_awaited_once()
        # Calling followup must not turn channel.send into followup.send.
        self.assertIs(channel.send, original_send)
        await channel.send("direct")
        self.assertEqual(original_send.await_count, 2)

    async def test_create_thread_from_starter_message(self):
        mod = load_cursor_plugin()
        starter = MagicMock()
        starter.create_thread = AsyncMock(return_value=SimpleNamespace(id=999, mention="<#999>"))
        parent = MagicMock()
        parent.create_thread = AsyncMock()
        thread = await mod._create_public_agent_thread(
            parent_channel=parent,
            starter_message=starter,
            thread_name="cursor-test",
        )
        self.assertEqual(thread.id, 999)
        starter.create_thread.assert_awaited_once()
        parent.create_thread.assert_not_called()
        kwargs = starter.create_thread.await_args.kwargs
        self.assertEqual(kwargs["name"], "cursor-test")
        self.assertEqual(kwargs["auto_archive_duration"], 60)

    async def test_create_thread_without_starter_uses_channel(self):
        mod = load_cursor_plugin()
        parent = MagicMock()
        parent.create_thread = AsyncMock(return_value=SimpleNamespace(id=888))
        thread = await mod._create_public_agent_thread(
            parent_channel=parent,
            starter_message=None,
            thread_name="cursor-slash",
        )
        self.assertEqual(thread.id, 888)
        parent.create_thread.assert_awaited_once()

    async def test_agent_prefix_roots_thread_on_start_message(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier1_user_ids": [GOD], "tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        mod._STATE.update(
            {
                "config": cfg,
                "sessions": MemorySessionStore(),
                "access": AccessController(
                    cfg,
                    MemoryAccessStore(),
                    image_retention=ImageRetentionStore(max_total_bytes=1),
                ),
                "policy_manager": ParentAllowsChildDeniesPolicy(),
                "require_policy": True,
                "bot": MagicMock(),
            }
        )
        message = MagicMock()
        message.id = 42
        message.content = "$agent fix the flaky test"
        message.attachments = []
        message.author = SimpleNamespace(id=int(T2), roles=[], display_name="Karma", name="karma")
        message.guild = SimpleNamespace(id=1)
        message.channel = SimpleNamespace(id=100, send=AsyncMock())
        message.reply = AsyncMock()
        ctx = SimpleNamespace(
            message=message,
            author=message.author,
            guild=message.guild,
            channel=message.channel,
        )
        with patch.object(mod, "_revalidate_run_auth", new=AsyncMock(return_value=None)):
            with patch.object(
                mod,
                "_build_context_from_message",
                new=AsyncMock(return_value=("fix the flaky test", [], [])),
            ):
                with patch.object(
                    mod, "_start_thread_bound_session", new=AsyncMock()
                ) as start:
                    await mod.handle_agent_prefix(ctx, "fix the flaky test")
        start.assert_awaited_once()
        kwargs = start.await_args.kwargs
        self.assertIs(kwargs["starter_message"], message)
        self.assertEqual(kwargs["parent_channel_id"], "100")
        self.assertEqual(kwargs["prompt"], "fix the flaky test")
        self.assertEqual(kwargs["prebuilt"][0], "fix the flaky test")

    async def test_agent_prefix_rejects_inside_thread(self):
        mod = load_cursor_plugin()
        message = MagicMock()
        message.attachments = []
        message.reply = AsyncMock()
        thread_channel = MagicMock(spec=discord.Thread)
        thread_channel.parent_id = 100
        ctx = SimpleNamespace(
            message=message,
            channel=thread_channel,
            author=SimpleNamespace(id=int(T2)),
            guild=SimpleNamespace(id=1),
        )
        with patch.object(mod, "_start_thread_bound_session", new=AsyncMock()) as start:
            await mod.handle_agent_prefix(ctx, "hello")
        start.assert_not_awaited()
        message.reply.assert_awaited()


if __name__ == "__main__":
    unittest.main()
