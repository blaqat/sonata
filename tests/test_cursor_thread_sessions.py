"""Thread-session UX tests for SONA-105 (/cursor new + bound threads)."""

from __future__ import annotations
from contextlib import contextmanager

import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from datetime import timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.access import AccessController, ImageRetentionStore, MemoryAccessStore
from cursor_cloud.config import load_cursor_config
from cursor_cloud.models import (
    AccessTier,
    AgentSession,
    GitBranchInfo,
    PendingDecision,
    RunRecord,
    RunSnapshot,
    RunStatus,
    ScopeKey,
    StreamEvent,
    ToolActivity,
    utcnow,
)
from cursor_cloud.run_tracker import RunTracker
from cursor_cloud.session_store import MemorySessionStore
from cursor_cloud.thread_renderer import (
    THREAD_THINKING_INDICATOR,
    format_thread_chat_info,
    github_hint_from_snapshot,
    render_thread_activity,
    render_thread_final,
    render_thread_summary,
)
from cursor_cloud.thread_session import (
    owner_reply_to_human,
    policy_channel_id,
    thread_session_immutable_violation,
)
from cursor_cloud.thread_sink import ThreadActivitySink
from cursor_cloud.thread_translate import (
    atranslate_final,
    translate_final,
)

# Injected dummy instructions for package-level translate machinery tests.
DUMMY_TRANSLATE_INSTRUCTIONS = (
    "DUMMY instructions: rewrite helpfully. Do NOT invent facts. Do NOT run commands."
)


GOD = "100000000000000001"
T2 = "100000000000000003"
OWNER = T2
OTHER = "100000000000000011"


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
    def test_thinking_indicator_uses_animated_emoji(self):
        self.assertEqual(
            THREAD_THINKING_INDICATOR,
            "<a:aithinking:1527850620273430548> *thinking...*",
        )

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

    def test_activity_lists_tools_before_thinking(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.RUNNING,
            thinking_text="planning the refactor",
            tools=[ToolActivity("1", "Read", "running", "keys=path")],
        )
        text = render_thread_activity(snap)
        self.assertLess(text.index("### Activity"), text.index("### Thinking"))

    def test_format_thread_chat_info_compact(self):
        text = format_thread_chat_info(
            agent_id="bc-agent-1",
            branch="cursor/demo-branch",
            model="claude-sonnet-4-6",
        )
        self.assertEqual(
            text,
            "### Chat Info\n"
            "- id: `bc-agent-1`\n"
            "- branch: `cursor/demo-branch`\n"
            "- model: `claude-sonnet-4-6`",
        )
        no_branch = format_thread_chat_info(agent_id="bc-agent-1", model=None)
        self.assertEqual(
            no_branch,
            "### Chat Info\n- id: `bc-agent-1`\n- model: `auto`",
        )
        self.assertNotIn("branch:", no_branch)

    def test_github_hint_prefers_branch_then_repo(self):
        from cursor_cloud.models import GitBranchInfo

        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            git_branches=[GitBranchInfo(branch="cursor/feat", pr_url=None)],
        )
        self.assertEqual(
            github_hint_from_snapshot(
                snap,
                repository_url="https://github.com/o/r",
            ),
            "cursor/feat",
        )
        self.assertEqual(
            github_hint_from_snapshot(
                RunSnapshot(run_id="r1", agent_id="a1", status=RunStatus.RUNNING),
                repository_url="https://github.com/o/r.git",
            ),
            "o/r",
        )

    def test_final_prepends_chat_info_only_when_requested(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="hello world",
        )
        header = format_thread_chat_info(
            agent_id="a1",
            branch="cursor/demo",
            model="gpt-5",
        )
        with_header = render_thread_final(snap, chat_info=header)
        without = render_thread_final(snap)
        self.assertTrue(with_header.startswith("### Chat Info"))
        self.assertIn("hello world", with_header)
        self.assertNotIn("### Chat Info", without)
        self.assertNotIn("### Git", with_header)
        self.assertNotIn("Run:", with_header)

    def test_render_thread_summary_sections_and_omissions(self):
        empty = render_thread_summary(
            RunSnapshot(run_id="r", agent_id="a", status=RunStatus.FINISHED)
        )
        self.assertEqual(empty, "")

        snap = RunSnapshot(
            run_id="r",
            agent_id="a",
            status=RunStatus.FINISHED,
            thinking_seconds=12.2,
            tool_family_counts={"search": 3, "read": 1, "shell": 2, "subagent": 2},
            subagents=[
                ToolActivity(
                    "t1", "Task", "completed", label="Inventory API credentials"
                ),
                ToolActivity("t2", "Task", "failed", label="Trace integrations"),
                ToolActivity("t3", "Task", "completed", label=""),
            ],
        )
        text = render_thread_summary(snap)
        self.assertIn("💭 Thought for 12s", text)
        self.assertIn("### Subagents", text)
        self.assertIn("🟢 Subagent 1: Inventory API credentials", text)
        self.assertIn("🔴 Subagent 2: Trace integrations", text)
        self.assertIn("🟢 Subagent 3", text)
        self.assertIn("### Tool Calls", text)
        self.assertIn("🔍 `search` ×3", text)
        self.assertIn("🐚 `shell` ×2", text)
        self.assertIn("📖 `read` ×1", text)
        self.assertNotIn("subagent", text.lower().split("tool calls", 1)[-1])
        # No thinking / empty counts omit those sections.
        bare = render_thread_summary(
            RunSnapshot(
                run_id="r",
                agent_id="a",
                status=RunStatus.FINISHED,
                subagents=[ToolActivity("t1", "Task", "completed", label="Only one")],
            )
        )
        self.assertNotIn("Thought for", bare)
        self.assertNotIn("### Tool Calls", bare)
        self.assertIn("🟢 Subagent 1: Only one", bare)

    def test_render_thread_summary_redacts_labels(self):
        snap = RunSnapshot(
            run_id="r",
            agent_id="a",
            status=RunStatus.FINISHED,
            subagents=[
                ToolActivity(
                    "t1",
                    "Task",
                    "completed",
                    label="ping @everyone please",
                )
            ],
        )
        text = render_thread_summary(snap)
        self.assertNotIn("@everyone", text)
        self.assertIn("Subagent 1:", text)

    def test_activity_idle_shows_thinking_indicator(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.QUEUED,
        )
        text = render_thread_activity(snap)
        self.assertEqual(text, THREAD_THINKING_INDICATOR)

    def test_activity_images_only_still_shows_thinking(self):
        """Skipped-image notes alone must not look like a dead pause."""
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.RUNNING,
        )
        text = render_thread_activity(
            snap, skipped_images=["duplicate: screenshot.png"]
        )
        self.assertIn(THREAD_THINKING_INDICATOR, text)
        self.assertIn("### Images", text)
        self.assertIn("duplicate:", text)

    def test_activity_terminal_does_not_say_done(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="the answer",
        )
        text = render_thread_activity(snap)
        self.assertNotIn("done", text.lower())
        self.assertNotIn("_done_", text)

    def test_activity_thinking_peek_still_renders(self):
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.RUNNING,
            thinking_text="considering the approach",
        )
        text = render_thread_activity(snap)
        self.assertIn("### Thinking", text)
        self.assertIn("considering the approach", text)
        self.assertNotEqual(text, THREAD_THINKING_INDICATOR)

    def test_activity_thinking_and_draft_use_head_tail_peek(self):
        thinking = (
            "Opening: trace how Discord attachments become vision inputs. "
            + ("Middle filler about unrelated queue bookkeeping details. " * 12)
            + "Closing: gemini flash describes the image for chat history."
        )
        draft = (
            "Here's the short version. "
            + ("Padding sentence that should not dominate the draft peek. " * 10)
            + "Queued URLs wait until the next interaction."
        )
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.RUNNING,
            thinking_text=thinking,
            assistant_text=draft,
        )
        text = render_thread_activity(snap)
        self.assertIn("### Thinking", text)
        self.assertIn("Discord attachments become vision", text)
        self.assertIn("gemini flash describes", text)
        self.assertIn("_Draft…_", text)
        self.assertIn("Here's the short version", text)
        self.assertIn("Queued URLs wait", text)
        self.assertIn("…", text)

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


class TestThreadTranslate(unittest.TestCase):
    def test_translate_injects_instructions_and_prompt(self):
        def fake_send(prompt, *args, **kwargs):
            self.assertEqual(prompt, "built prompt body")
            self.assertEqual(kwargs.get("AI"), "Claude")
            self.assertNotIn("model", kwargs)
            cfg = kwargs.get("config") or {}
            self.assertEqual(cfg.get("instructions"), DUMMY_TRANSLATE_INSTRUCTIONS)
            self.assertFalse(cfg.get("agent"))
            return "rewritten final"

        out = translate_final(
            "The bug was fixed in auth.py.",
            send=fake_send,
            instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
            prompt="built prompt body",
            ai="Claude",
        )
        self.assertEqual(out, "rewritten final")

    def test_translate_defaults_prompt_to_text(self):
        def fake_send(prompt, *args, **kwargs):
            self.assertEqual(prompt, "original agent text")
            return "ok"

        out = translate_final(
            "original agent text",
            send=fake_send,
            instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
        )
        self.assertEqual(out, "ok")

    def test_translate_passes_explicit_model_when_set(self):
        def fake_send(prompt, *args, **kwargs):
            self.assertEqual(kwargs.get("AI"), "OpenAI")
            self.assertEqual(kwargs.get("model"), "gpt-test")
            return "rewritten"

        out = translate_final(
            "original",
            send=fake_send,
            instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
            ai="OpenAI",
            model="gpt-test",
        )
        self.assertEqual(out, "rewritten")

    def test_translate_fallback_on_send_failure(self):
        def boom(*_a, **_k):
            raise RuntimeError("ai down")

        original = "The bug was fixed in auth.py."
        out = translate_final(
            original,
            send=boom,
            instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
        )
        self.assertEqual(out, original)

    def test_translate_skips_errors_and_empty(self):
        calls = {"n": 0}

        def fake_send(*_a, **_k):
            calls["n"] += 1
            return "should not run"

        self.assertEqual(
            translate_final(
                "### Error\nbad",
                send=fake_send,
                instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
            ),
            "### Error\nbad",
        )
        self.assertEqual(
            translate_final(
                "_No output._",
                send=fake_send,
                instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
            ),
            "_No output._",
        )
        self.assertEqual(calls["n"], 0)

    def test_translate_fallback_when_send_or_instructions_missing(self):
        original = "plain cursor final"
        self.assertEqual(translate_final(original), original)
        self.assertEqual(
            translate_final(original, send=lambda *_a, **_k: "x"),
            original,
        )
        self.assertEqual(
            translate_final(
                original,
                send=lambda *_a, **_k: "x",
                instructions="   ",
            ),
            original,
        )


class TestThreadTranslateAsync(unittest.IsolatedAsyncioTestCase):
    async def test_atranslate_timeout_falls_back(self):
        def slow_send(*_a, **_k):
            import time

            time.sleep(0.2)
            return "too late"

        original = "cursor final text"
        out = await atranslate_final(
            original,
            send=slow_send,
            instructions=DUMMY_TRANSLATE_INSTRUCTIONS,
            timeout=0.01,
        )
        self.assertEqual(out, original)

    async def test_plugin_translate_uses_live_prompt_manager(self):
        mod = load_cursor_plugin()
        seen = {}
        # Live get_instructions must NOT be used (includes $command tool list).
        live_instructions = (
            "LIVE instructions with Command Guidelines:\n"
            "- Command List: search\n"
            "- Start response with $"
        )

        def fake_send(prompt, *args, **kwargs):
            seen["prompt"] = prompt
            seen.update(kwargs)
            return "sona voice"

        live_pm = SimpleNamespace(
            send=fake_send,
            get_instructions=lambda *a, **k: live_instructions,
        )
        cfg = SimpleNamespace(get=lambda key, *a: "Claude" if key == "AI" else None)
        sona = SimpleNamespace(config=cfg, prompt_manager=live_pm)
        mod.reset_runtime(bot=SimpleNamespace(sonata=sona))

        # Stale module-level PROMPT_MANAGER must not be used when live PM exists.
        stale_calls = {"n": 0}

        def stale_send(*_a, **_k):
            stale_calls["n"] += 1
            return "stale"

        with patch_cursor(mod, "PROMPT_MANAGER", SimpleNamespace(send=stale_send)):
            out = await mod._translate_thread_final_for_sona(
                "cursor facts here",
                user_prompt="what did the agent find",
                user_name="blaqat",
            )

        self.assertEqual(out, "sona voice")
        self.assertEqual(stale_calls["n"], 0)
        self.assertEqual(seen.get("AI"), "Claude")
        self.assertNotIn("model", seen)
        instr = (seen.get("config") or {}).get("instructions") or ""
        self.assertEqual(instr, mod.DEFAULT_SONA_INSTRUCTIONS)
        self.assertNotIn("Command List:", instr)
        self.assertFalse((seen.get("config") or {}).get("agent"))
        self.assertIn("coding agent finished", seen["prompt"].lower())
        self.assertIn("cursor facts here", seen["prompt"])
        self.assertIn("what did the agent find", seen["prompt"])
        self.assertIn("BEG OF CHAT LOG", seen["prompt"])
        self.assertIs(mod._live_prompt_manager(), live_pm)


class TestThreadTranslatePersona(unittest.TestCase):
    """Persona constants and prompt shape live in the plugin, not cursor_cloud."""

    def test_plugin_persona_instructions_shape(self):
        mod = load_cursor_plugin()
        instr = mod.DEFAULT_SONA_INSTRUCTIONS
        self.assertEqual(instr, mod.build_sona_thread_system_instructions())
        self.assertIn("smart alec", instr.lower())
        self.assertIn("output guidelines", instr.lower())
        self.assertIn("brevity is secondary to completeness", instr.lower())
        self.assertIn("do not truncate for style", instr.lower())
        self.assertNotIn("Command Guidelines", instr)
        self.assertNotIn("Command List:", instr)

    def test_plugin_user_prompt_selfcommand_shape(self):
        mod = load_cursor_plugin()
        prompt = mod._build_user_prompt(
            "The bug was fixed in auth.py.",
            user="blaqat",
            message="please fix auth",
        )
        self.assertIn("coding agent finished", prompt.lower())
        self.assertIn("The bug was fixed in auth.py.", prompt)
        self.assertIn("BEG OF CHAT LOG", prompt)
        self.assertIn("please fix auth", prompt)
        self.assertIn("blaqat:", prompt)
        self.assertNotIn("Command Guidelines", prompt)
        self.assertNotIn("Rewrite the following", prompt)


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

    async def test_long_final_splits_into_two_messages(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        sink = ThreadActivitySink(channel, activity, edit_interval_ms=0)
        # Two clear paragraphs that together exceed Discord's 2000 limit.
        part_a = ("Opening paragraph with concrete findings. " * 40).strip()
        part_b = ("Closing paragraph with the remaining details. " * 40).strip()
        body = part_a + "\n\n" + part_b
        self.assertGreater(len(body), 2000)
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text=body,
        )
        await sink.update_from_snapshot(snap, terminal=True)
        self.assertEqual(channel.send.await_count, 2)
        first = channel.send.await_args_list[0].args[0]
        second = channel.send.await_args_list[1].args[0]
        self.assertLessEqual(len(first), 2000)
        self.assertLessEqual(len(second), 2000)
        self.assertIn("Opening paragraph", first)
        self.assertIn("Closing paragraph", second)
        self.assertNotIn("…(truncated)", first)

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

    async def test_finished_final_uses_translator(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()

        async def translate(text: str) -> str:
            return f"sona:{text}"

        sink = ThreadActivitySink(
            channel,
            activity,
            edit_interval_ms=0,
            final_translator=translate,
        )
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="done",
        )
        await sink.update_from_snapshot(snap, terminal=True)
        sent = channel.send.await_args.args[0]
        self.assertTrue(sent.startswith("sona:"))

    async def test_first_final_includes_chat_info_once(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        sink = ThreadActivitySink(
            channel,
            activity,
            edit_interval_ms=0,
            include_chat_info=True,
            chat_info_model="claude-sonnet-4-6",
            chat_info_repository_url="https://github.com/o/r",
        )
        snap = RunSnapshot(
            run_id="r1",
            agent_id="bc-agent-1",
            status=RunStatus.FINISHED,
            result_text="done",
            git_branches=[GitBranchInfo(branch="cursor/feat")],
            thinking_seconds=5.0,
            tool_family_counts={"search": 2},
        )
        await sink.update_from_snapshot(snap, terminal=True)
        await sink.update_from_snapshot(snap, terminal=True)
        edited = (
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0]
        )
        self.assertTrue(edited.startswith("### Chat Info"))
        self.assertIn("bc-agent-1", edited)
        self.assertIn("claude-sonnet-4-6", edited)
        self.assertIn("cursor/feat", edited)
        # summary then answer
        self.assertEqual(channel.send.await_count, 2)
        summary_sent = channel.send.await_args_list[0].args[0]
        answer_sent = channel.send.await_args_list[1].args[0]
        self.assertIn("Thought for", summary_sent)
        self.assertIn("🔍 `search` ×2", summary_sent)
        self.assertEqual(answer_sent, "done")
        self.assertNotIn("### Chat Info", answer_sent)

    async def test_chat_info_survives_sona_translator(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        seen: list[str] = []

        async def translate(text: str) -> str:
            seen.append(text)
            return f"sona:{text}"

        sink = ThreadActivitySink(
            channel,
            activity,
            edit_interval_ms=0,
            final_translator=translate,
            include_chat_info=True,
            chat_info_model="claude-sonnet-4-6",
            chat_info_repository_url="https://github.com/o/r",
        )
        snap = RunSnapshot(
            run_id="r1",
            agent_id="bc-agent-1",
            status=RunStatus.FINISHED,
            result_text="done",
        )
        await sink.update_from_snapshot(snap, terminal=True)
        self.assertEqual(seen, ["done"])
        edited = (
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0]
        )
        self.assertTrue(edited.startswith("### Chat Info"))
        self.assertIn("bc-agent-1", edited)
        sent = channel.send.await_args.args[0]
        self.assertEqual(sent, "sona:done")
        self.assertNotIn("### Chat Info", sent)

    async def test_later_run_edits_activity_into_summary(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        sink = ThreadActivitySink(channel, activity, edit_interval_ms=0)
        snap = RunSnapshot(
            run_id="r2",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="second answer",
            thinking_seconds=3.0,
            tool_family_counts={"shell": 1},
        )
        await sink.update_from_snapshot(snap, terminal=True)
        edited = (
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0]
        )
        self.assertIn("Thought for 3s", edited)
        self.assertIn("🐚 `shell` ×1", edited)
        self.assertEqual(channel.send.await_count, 1)
        self.assertEqual(channel.send.await_args.args[0], "second answer")

    async def test_first_then_followups_keep_per_run_summaries(self):
        """Regression: each follow-up keeps its own summary before its answer."""

        class ScriptedClient:
            def __init__(self, events):
                self._events = list(events)

            async def stream_run_with_fallback(self, *a, **k):
                for event in self._events:
                    yield event

            async def stream_run(self, *a, **k):
                if False:  # pragma: no cover - async generator
                    yield None
                raise AssertionError("resume should not be needed for healthy SSE")

        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=99))
        # Fresh activity message per run (mirrors handle_thread_message).
        activities = [MagicMock(id=i) for i in (1, 2, 3)]
        for activity in activities:
            activity.edit = AsyncMock()

        # Run 1: Chat Info + summary message + answer
        sink1 = ThreadActivitySink(
            channel,
            activities[0],
            edit_interval_ms=0,
            include_chat_info=True,
            chat_info_model="auto",
        )
        tracker1 = RunTracker(ScriptedClient([
            StreamEvent("status", {"runId": "r1", "status": "RUNNING"}),
            StreamEvent("thinking", {"text": "plan"}),
            StreamEvent(
                "tool_call",
                {
                    "callId": "t1",
                    "name": "Task",
                    "status": "completed",
                    "args": {"description": "Explore repo"},
                },
            ),
            StreamEvent(
                "tool_call",
                {
                    "callId": "t2",
                    "name": "grep",
                    "status": "completed",
                    "args": {"pattern": "x"},
                },
            ),
            StreamEvent(
                "result",
                {
                    "runId": "r1",
                    "status": "FINISHED",
                    "text": "first answer",
                    "git": {"branches": [{"branch": "cursor/feat"}]},
                },
            ),
            StreamEvent("done", {}),
        ]), sink1, edit_interval_ms=10_000)
        await tracker1.track("bc", "r1")

        first_edit = (
            activities[0].edit.await_args.kwargs.get("content")
            or activities[0].edit.await_args.args[0]
        )
        self.assertTrue(first_edit.startswith("### Chat Info"))
        self.assertEqual(channel.send.await_count, 2)
        self.assertIn("Thought for", channel.send.await_args_list[0].args[0])
        self.assertIn("### Subagents", channel.send.await_args_list[0].args[0])
        self.assertIn("🔍 `search` ×1", channel.send.await_args_list[0].args[0])
        self.assertEqual(channel.send.await_args_list[1].args[0], "first answer")

        # Follow-up 1 — production path: first SSE unavailable, resume recovers tools.
        channel.send.reset_mock()
        sink2 = ThreadActivitySink(channel, activities[1], edit_interval_ms=0)

        class FollowUpRaceClient:
            def __init__(self):
                self.stream_attempts = 0

            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_unavailable",
                        "message": "Run stream is no longer available",
                    },
                )

            async def stream_run(self, agent_id, run_id, *, last_event_id=None):
                del agent_id, run_id, last_event_id
                self.stream_attempts += 1
                if self.stream_attempts < 2:
                    from cursor_cloud.errors import AgentRunError

                    raise AgentRunError(
                        "Run stream is no longer available",
                        code="stream_unavailable",
                    )
                yield StreamEvent("status", {"runId": "r2", "status": "RUNNING"})
                yield StreamEvent("thinking", {"text": "notion next"})
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "m1",
                        "name": "mcp",
                        "status": "completed",
                        "args": {"toolName": "search", "serverName": "notion"},
                    },
                )
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "m2",
                        "name": "mcp",
                        "status": "completed",
                        "args": {"toolName": "fetch", "serverName": "notion"},
                    },
                )
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "s1",
                        "name": "Shell",
                        "status": "completed",
                        "args": {"command": "echo hi"},
                    },
                )
                yield StreamEvent(
                    "result",
                    {"runId": "r2", "status": "FINISHED", "text": "second answer"},
                )
                yield StreamEvent("done", {})

            async def get_run(self, agent_id, run_id):
                if self.stream_attempts < 2:
                    return RunRecord(
                        id=run_id,
                        agent_id=agent_id,
                        status=RunStatus.RUNNING,
                    )
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="second answer",
                )

        tracker2 = RunTracker(
            FollowUpRaceClient(),
            sink2,
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        await tracker2.track("bc", "r2", initial_status=RunStatus.CREATING)

        follow1_edit = (
            activities[1].edit.await_args.kwargs.get("content")
            or activities[1].edit.await_args.args[0]
        )
        self.assertIn("Thought for", follow1_edit)
        self.assertIn("`mcp:search` ×1", follow1_edit)
        self.assertIn("`mcp:fetch` ×1", follow1_edit)
        self.assertIn("🐚 `shell` ×1", follow1_edit)
        self.assertNotIn("### Chat Info", follow1_edit)
        self.assertEqual(channel.send.await_count, 1)
        self.assertEqual(channel.send.await_args.args[0], "second answer")

        # Follow-up 2 with different counts — chronological independence
        channel.send.reset_mock()
        sink3 = ThreadActivitySink(channel, activities[2], edit_interval_ms=0)
        tracker3 = RunTracker(ScriptedClient([
            StreamEvent("status", {"runId": "r3", "status": "RUNNING"}),
            StreamEvent("thinking", {"text": "wrap up"}),
            StreamEvent(
                "tool_call",
                {
                    "callId": "r1",
                    "name": "Read",
                    "status": "completed",
                    "args": {"path": "a.py"},
                },
            ),
            StreamEvent(
                "tool_call",
                {
                    "callId": "r2",
                    "name": "Read",
                    "status": "completed",
                    "args": {"path": "b.py"},
                },
            ),
            StreamEvent(
                "result",
                {"runId": "r3", "status": "FINISHED", "text": "third answer"},
            ),
            StreamEvent("done", {}),
        ]), sink3, edit_interval_ms=10_000)
        await tracker3.track("bc", "r3")

        follow2_edit = (
            activities[2].edit.await_args.kwargs.get("content")
            or activities[2].edit.await_args.args[0]
        )
        self.assertIn("Thought for", follow2_edit)
        self.assertIn("📖 `read` ×2", follow2_edit)
        self.assertNotIn("mcp:", follow2_edit)
        self.assertNotIn("shell", follow2_edit)
        self.assertEqual(channel.send.await_args.args[0], "third answer")
        # Prior activity slots remain untouched after their terminal edit.
        self.assertTrue(
            (
                activities[0].edit.await_args.kwargs.get("content")
                or activities[0].edit.await_args.args[0]
            ).startswith("### Chat Info")
        )
        self.assertIn(
            "`mcp:search` ×1",
            activities[1].edit.await_args.kwargs.get("content")
            or activities[1].edit.await_args.args[0],
        )

    async def test_later_run_empty_summary_uses_zwsp(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        sink = ThreadActivitySink(channel, activity, edit_interval_ms=0)
        snap = RunSnapshot(
            run_id="r3",
            agent_id="a1",
            status=RunStatus.FINISHED,
            result_text="ok",
        )
        await sink.update_from_snapshot(snap, terminal=True)
        edited = (
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0]
        )
        self.assertEqual(edited, "\u200b")
        self.assertEqual(channel.send.await_args.args[0], "ok")

    async def test_chat_info_failure_still_sends_answer(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock(side_effect=RuntimeError("edit failed"))
        sink = ThreadActivitySink(
            channel,
            activity,
            edit_interval_ms=0,
            include_chat_info=True,
            chat_info_model="auto",
        )
        snap = RunSnapshot(
            run_id="r1",
            agent_id="bc-1",
            status=RunStatus.FINISHED,
            result_text="still here",
            thinking_seconds=2.0,
        )
        await sink.update_from_snapshot(snap, terminal=True)
        self.assertTrue(sink.degraded)
        # summary + answer still attempted
        self.assertGreaterEqual(channel.send.await_count, 1)
        self.assertEqual(channel.send.await_args_list[-1].args[0], "still here")

    async def test_error_final_skips_translator(self):
        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        translator = AsyncMock(return_value="witty fail")
        sink = ThreadActivitySink(
            channel,
            activity,
            edit_interval_ms=0,
            final_translator=translator,
        )
        snap = RunSnapshot(
            run_id="r1",
            agent_id="a1",
            status=RunStatus.ERROR,
            error_message="boom",
        )
        await sink.update_from_snapshot(snap, terminal=True)
        translator.assert_not_awaited()
        sent = channel.send.await_args.args[0]
        self.assertIn("Error", sent)
        self.assertIn("boom", sent)


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
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=access,
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(),
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

        with patch_cursor(mod, "prepare", new=AsyncMock(return_value=mod.ApprovalPending())) as prep:
            with patch_cursor(mod, "launch", new=AsyncMock()) as launch:
                handled = await mod.handle_thread_message(message)
        self.assertTrue(handled)
        prep.assert_awaited_once()
        launch.assert_not_awaited()

    async def test_non_owner_and_human_reply_ignored(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {"enabled": True, "default_repository_url": "https://github.com/o/r"},
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(cfg, MemoryAccessStore()),
            policy_manager=ParentAllowsChildDeniesPolicy(),
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
        with patch_cursor(mod, "prepare", new=AsyncMock()) as prep:
            self.assertTrue(await mod.handle_thread_message(msg_other))
            self.assertTrue(await mod.handle_thread_message(msg_owner_reply))
        prep.assert_not_awaited()

    async def test_bot_messages_ignored(self):
        mod = load_cursor_plugin()
        sessions = MemorySessionStore()
        mod.reset_runtime(sessions=sessions)
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
        mod.reset_runtime(
            config=cfg,
            access=AccessController(cfg, MemoryAccessStore()),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
        )
        tier = await mod._revalidate_run_auth(
            mod.get_runtime(),
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
                mod.get_runtime(),
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
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=access,
            access_store=store,
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            client=MagicMock(),
            bot=MagicMock(),
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
        original_send = channel.send

        interaction = SimpleNamespace(
            user=SimpleNamespace(id=int(GOD), roles=[]),
            guild=SimpleNamespace(
                id=1,
                get_channel=MagicMock(return_value=channel),
                get_thread=MagicMock(return_value=None),
            ),
            channel=channel,
            client=SimpleNamespace(
                get_channel=MagicMock(return_value=None),
                fetch_channel=AsyncMock(return_value=channel),
            ),
            message=None,
            response=SimpleNamespace(is_done=MagicMock(return_value=True)),
            followup=SimpleNamespace(send=AsyncMock()),
        )

        access.images.get = AsyncMock(return_value=[])
        access.images.discard = AsyncMock()
        with patch_cursor(mod, "launch", new=AsyncMock()) as launch_fn:
            with patch_cursor(mod, "_ephemeral", new=AsyncMock()):
                await mod._launch_approved_request(interaction, req)

        launch_fn.assert_awaited_once()
        _rt, ui, prepared = launch_fn.await_args.args
        self.assertTrue(prepared.ctx.thread_bound)
        self.assertEqual(prepared.ctx.parent_channel_id, "100")
        self.assertTrue(prepared.ctx.skip_status_post)
        self.assertIs(prepared.ctx.status_msg, activity)
        # Regression: approved launch must not monkey-patch channel.send.
        self.assertIsNot(ui.followup, channel)
        self.assertIs(channel.send, original_send)

    async def test_approved_launch_shim_does_not_patch_channel_send(self):
        """Approve-once used to set followup=channel then overwrite send → RecursionError."""
        mod = load_cursor_plugin()
        channel = MagicMock()
        channel.id = 200
        channel.send = AsyncMock(return_value=SimpleNamespace(id=1))
        original_send = channel.send
        shim = mod._interaction_shim_for_channel(
            channel,
            user_id=OWNER,
            guild_id=1,
            guild=SimpleNamespace(id=1),
            client=None,
        )
        self.assertIs(channel.send, original_send)
        self.assertIsNot(shim.followup, channel)
        await shim.followup.send("hello")
        self.assertIs(channel.send, original_send)
        channel.send.assert_awaited()


class TestSessionThreadFieldsCompat(unittest.TestCase):
    def test_agent_session_roundtrip_and_legacy(self):
        session = AgentSession(
            scope=ScopeKey("1", "200", OWNER),
            agent_id="bc-1",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            latest_run_id="run-1",
            latest_git=[GitBranchInfo(branch="cursor/demo", pr_url=None)],
        )
        restored = AgentSession.from_dict(session.to_dict())
        self.assertTrue(restored.thread_bound)
        self.assertEqual(restored.parent_channel_id, "100")
        self.assertEqual(restored.latest_git[0].branch, "cursor/demo")
        # Legacy raw dicts in latest_git still deserialize.
        from_raw = AgentSession.from_dict(
            {
                "scope": {"guild_id": "1", "channel_id": "200", "user_id": OWNER},
                "agent_id": "bc-raw-git",
                "owner_id": OWNER,
                "latest_git": [{"branch": "cursor/demo", "pr_url": None}],
            }
        )
        self.assertEqual(from_raw.latest_git[0].branch, "cursor/demo")
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

    def _fake_interaction(self):
        channel = MagicMock()
        channel.id = 100
        return SimpleNamespace(
            response=SimpleNamespace(
                is_done=lambda: True,
                defer=AsyncMock(),
                send_message=AsyncMock(),
            ),
            followup=SimpleNamespace(send=AsyncMock()),
            channel=channel,
            channel_id=100,
            guild_id=1,
            user=SimpleNamespace(id=1, roles=[], name="u", display_name="U"),
            client=None,
        )

    def _fake_prepared(self, mod):
        scope = ScopeKey("1", "999", "1")
        ctx = mod.RunContext(
            scope=scope,
            role_ids=[],
            thread_bound=True,
            parent_channel_id="100",
            policy_channel_id="100",
            status_msg=None,
            subcommand="new",
        )
        from cursor_cloud.models import RunRequestEnvelope

        env = RunRequestEnvelope(
            requester_id="1",
            scope=scope,
            prompt_text="x",
            model=None,
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
        )
        return mod.PreparedRun(
            ctx=ctx,
            prompt_text="x",
            images=[],
            skipped=[],
            envelope=env,
            force_new=True,
            agent_id=None,
        )

    async def test_start_skips_success_notify_for_starter_message(self):
        mod = load_cursor_plugin()
        notify = AsyncMock()
        thread = SimpleNamespace(
            id=999, mention="<#999>", send=AsyncMock(return_value=SimpleNamespace(id=1, channel=None))
        )
        thread.send.return_value.channel = thread
        starter = MagicMock()
        prepared = self._fake_prepared(mod)
        with patch_cursor(mod, "_generate_session_title", new=AsyncMock(return_value="ispy overview")):
            with patch_cursor(mod, "_create_public_agent_thread", new=AsyncMock(return_value=thread)
            ):
                with patch_cursor(mod, "prepare", new=AsyncMock(return_value=prepared)
                ) as prep:
                    with patch_cursor(mod, "launch", new=AsyncMock()):
                        await mod._start_thread_bound_session(
                            interaction=self._fake_interaction(),
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
        prepared = self._fake_prepared(mod)
        with patch_cursor(mod, "_generate_session_title", new=AsyncMock(return_value="slash title")):
            with patch_cursor(mod, "_create_public_agent_thread", new=AsyncMock(return_value=thread)
            ):
                with patch_cursor(mod, "prepare", new=AsyncMock(return_value=prepared)):
                    with patch_cursor(mod, "launch", new=AsyncMock()):
                        await mod._start_thread_bound_session(
                            interaction=self._fake_interaction(),
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

    async def test_start_skips_approval_pending_notify(self):
        mod = load_cursor_plugin()
        notify = AsyncMock()
        thread = SimpleNamespace(
            id=999, mention="<#999>", send=AsyncMock(return_value=SimpleNamespace(id=1))
        )
        thread.send.return_value.channel = thread
        with patch_cursor(mod, "_generate_session_title", new=AsyncMock(return_value="t")):
            with patch_cursor(mod, "_create_public_agent_thread", new=AsyncMock(return_value=thread)
            ):
                with patch_cursor(mod,
                    "prepare",
                    new=AsyncMock(return_value=mod.ApprovalPending(request_id="r1")),
                ):
                    await mod._start_thread_bound_session(
                        interaction=self._fake_interaction(),
                        prompt="hello",
                        message_ref=None,
                        images=[],
                        parent_channel=MagicMock(),
                        parent_channel_id="100",
                        user=SimpleNamespace(id=1, name="u", display_name="U"),
                        guild_id=1,
                        starter_message=MagicMock(),
                        notify=notify,
                    )
                    await mod._start_thread_bound_session(
                        interaction=self._fake_interaction(),
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
        notify.assert_not_awaited()


class TestThreadFollowupIndicator(unittest.IsolatedAsyncioTestCase):
    async def test_followup_skips_activity_when_gated(self):
        """Idle/approval gates must not leave a thinking message above the check."""
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
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(),
        )
        prior = MagicMock()
        prior.id = 55
        prior.content = "### Chat Info\n- id: `bc-1`\n- model: `auto`"
        prior.edit = AsyncMock()
        channel = MagicMock()
        channel.id = 200
        channel.parent_id = 100
        channel.fetch_message = AsyncMock(return_value=prior)
        channel.send = AsyncMock()
        message = MagicMock()
        message.id = 901
        message.author = SimpleNamespace(id=int(OWNER), bot=False, roles=[])
        message.content = "follow up please"
        message.attachments = []
        message.reference = None
        message.channel = channel
        message.guild = SimpleNamespace(id=1)
        with patch_cursor(mod, "_channel_is_thread", return_value=True):
            with patch_cursor(mod, "_revalidate_run_auth", new=AsyncMock()):
                with patch_cursor(mod,
                    "_build_context_from_message",
                    new=AsyncMock(return_value=("follow up please", [], [])),
                ):
                    with patch_cursor(mod, "prepare", new=AsyncMock(return_value=mod.DecisionPending(kind="idle"))
                    ) as prep:
                        with patch_cursor(mod, "launch", new=AsyncMock()) as launch_fn:
                            ok = await mod.handle_thread_message(message)
        self.assertTrue(ok)
        prior.edit.assert_not_awaited()
        channel.fetch_message.assert_not_awaited()
        channel.send.assert_not_awaited()
        launch_fn.assert_not_awaited()
        loaded = await sessions.get_session(scope, "bc-1")
        self.assertEqual(loaded.status_message_id, "55")
        self.assertIsNone(prep.await_args.kwargs.get("status_msg"))
        self.assertTrue(prep.await_args.kwargs.get("skip_status_post"))

    async def test_followup_posts_fresh_activity_after_prepare(self):
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
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(),
        )
        new_activity = MagicMock()
        new_activity.id = 99
        channel = MagicMock()
        channel.id = 200
        channel.parent_id = 100
        channel.fetch_message = AsyncMock()
        channel.send = AsyncMock(return_value=new_activity)
        message = MagicMock()
        message.id = 902
        message.author = SimpleNamespace(id=int(OWNER), bot=False, roles=[])
        message.content = "another follow up"
        message.attachments = []
        message.reference = None
        message.channel = channel
        message.guild = SimpleNamespace(id=1)
        prepared = MagicMock(spec=mod.PreparedRun)
        prepared.ctx = SimpleNamespace(status_msg=None, skip_status_post=True)
        with patch_cursor(mod, "_channel_is_thread", return_value=True):
            with patch_cursor(mod, "_revalidate_run_auth", new=AsyncMock()):
                with patch_cursor(mod,
                    "_build_context_from_message",
                    new=AsyncMock(return_value=("another follow up", [], [])),
                ):
                    with patch_cursor(mod, "prepare", new=AsyncMock(return_value=prepared)
                    ) as prep:
                        with patch_cursor(mod, "launch", new=AsyncMock()) as launch_fn:
                            ok = await mod.handle_thread_message(message)
        self.assertTrue(ok)
        channel.fetch_message.assert_not_awaited()
        channel.send.assert_awaited()
        self.assertEqual(
            channel.send.await_args.args[0]
            if channel.send.await_args.args
            else channel.send.await_args.kwargs.get("content"),
            THREAD_THINKING_INDICATOR,
        )
        loaded = await sessions.get_session(scope, "bc-1")
        self.assertEqual(loaded.status_message_id, "99")
        self.assertIsNone(prep.await_args.kwargs.get("status_msg"))
        launch_fn.assert_awaited_once()
        self.assertIs(prepared.ctx.status_msg, new_activity)
        self.assertTrue(prepared.ctx.skip_status_post)

    async def test_idle_offer_is_single_combined_channel_message(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "session_idle_prompt_minutes": 10,
                "access": {"tier1_user_ids": [GOD], "tier2_user_ids": [OWNER]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        scope = ScopeKey("1", "200", OWNER)
        session = AgentSession(
            scope=scope,
            agent_id="bc-idle",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="55",
            active=True,
            latest_run_status=RunStatus.FINISHED,
            last_meaningful_activity_at=utcnow() - timedelta(minutes=30),
        )
        await sessions.upsert(session)
        await sessions.set_active(scope, "bc-idle")
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(add_view=MagicMock()),
        )
        decision_msg = MagicMock()
        decision_msg.id = 777
        decision_msg.channel = MagicMock(id=200)
        channel = MagicMock()
        channel.id = 200
        channel.parent_id = 100
        channel.send = AsyncMock(return_value=decision_msg)
        message = MagicMock()
        message.id = 903
        message.author = SimpleNamespace(id=int(OWNER), bot=False, roles=[])
        message.content = "are you still there"
        message.attachments = []
        message.reference = None
        message.channel = channel
        message.guild = SimpleNamespace(id=1)
        with patch_cursor(mod, "_channel_is_thread", return_value=True):
            with patch_cursor(mod, "_revalidate_run_auth", new=AsyncMock(return_value=AccessTier.ADMIN)):
                with patch_cursor(mod,
                    "_build_context_from_message",
                    new=AsyncMock(return_value=("are you still there", [], [])),
                ):
                    with patch_cursor(mod, "launch", new=AsyncMock()) as launch_fn:
                        ok = await mod.handle_thread_message(message)
        self.assertTrue(ok)
        launch_fn.assert_not_awaited()
        channel.send.assert_awaited_once()
        content = (
            channel.send.await_args.args[0]
            if channel.send.await_args.args
            else channel.send.await_args.kwargs.get("content")
        )
        self.assertIn("Session `bc-idle` is idle", content)
        self.assertIn("choose how to proceed", content)
        self.assertNotIn("Session idle — choose how to proceed in the channel message", content)
        self.assertNotIn("### Idle session", content)
        self.assertIsNotNone(channel.send.await_args.kwargs.get("view"))
        loaded = await sessions.get_session(scope, "bc-idle")
        self.assertEqual(loaded.status_message_id, "55")

    async def test_idle_continue_edits_to_continuing_then_posts_thinking(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier1_user_ids": [GOD], "tier2_user_ids": [OWNER]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        scope = ScopeKey("1", "200", OWNER)
        session = AgentSession(
            scope=scope,
            agent_id="bc-idle",
            owner_id=OWNER,
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="55",
            active=True,
            latest_run_status=RunStatus.FINISHED,
        )
        await sessions.upsert(session)
        await sessions.set_active(scope, "bc-idle")
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(),
        )
        decision_message = MagicMock()
        decision_message.edit = AsyncMock()
        activity = MagicMock()
        activity.id = 88
        channel = MagicMock()
        channel.id = 200
        channel.send = AsyncMock(return_value=activity)
        interaction = MagicMock()
        interaction.user = SimpleNamespace(id=int(OWNER), roles=[])
        interaction.channel = channel
        interaction.message = decision_message
        interaction.response = SimpleNamespace(is_done=MagicMock(return_value=True))
        interaction.followup = SimpleNamespace(send=AsyncMock())
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_t",
                scope=scope,
                agent_id="bc-idle",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
                message_channel_id="200",
                message_id="777",
            )
        )
        await sessions.save_pending_payload(
            "idle_t",
            {
                "prompt": "continue me",
                "prompt_text": "continue me",
                "skipped": [],
                "image_metas": [],
                "prepared_meta": {
                    "thread_bound": True,
                    "parent_channel_id": "100",
                    "policy_channel_id": "100",
                    "subcommand": "run",
                },
            },
        )
        ui = mod.InteractionUI(interaction)
        prepared = MagicMock(spec=mod.PreparedRun)
        prepared.ctx = SimpleNamespace(status_msg=None, skip_status_post=False)
        with patch_cursor(mod, "_revalidate_run_auth", new=AsyncMock()):
            with patch_cursor(mod, "prepare", new=AsyncMock(return_value=prepared)) as prep:
                with patch_cursor(mod, "launch", new=AsyncMock()) as launch_fn:
                    await mod.complete_decision(mod.get_runtime(), ui, "idle_t", "continue")
        decision_message.edit.assert_awaited()
        self.assertEqual(
            decision_message.edit.await_args.kwargs.get("content"),
            "Continuing session...",
        )
        channel.send.assert_awaited_once()
        self.assertEqual(
            channel.send.await_args.args[0]
            if channel.send.await_args.args
            else channel.send.await_args.kwargs.get("content"),
            THREAD_THINKING_INDICATOR,
        )
        self.assertIs(prep.await_args.kwargs.get("status_msg"), activity)
        self.assertTrue(prep.await_args.kwargs.get("skip_status_post"))
        launch_fn.assert_awaited_once()
        loaded = await sessions.get_session(scope, "bc-idle")
        self.assertEqual(loaded.status_message_id, "88")


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
        mod.reset_runtime(
            config=cfg,
            sessions=MemorySessionStore(),
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(),
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
        with patch_cursor(mod, "_revalidate_run_auth", new=AsyncMock(return_value=None)):
            with patch_cursor(mod,
                "_build_context_from_message",
                new=AsyncMock(return_value=("fix the flaky test", [], [])),
            ):
                with patch_cursor(mod, "_start_thread_bound_session", new=AsyncMock()
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
        with patch_cursor(mod, "_start_thread_bound_session", new=AsyncMock()) as start:
            await mod.handle_agent_prefix(ctx, "hello")
        start.assert_not_awaited()
        message.reply.assert_awaited()


class TestCursorSessionsParentFilter(unittest.IsolatedAsyncioTestCase):
    async def test_parent_lists_only_this_channels_thread_sessions(self):
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
        await sessions.upsert(
            AgentSession(
                scope=ScopeKey("1", "200", OWNER),
                agent_id="bc-here",
                owner_id=OWNER,
                thread_bound=True,
                parent_channel_id="100",
                name="here",
                active=True,
            )
        )
        await sessions.upsert(
            AgentSession(
                scope=ScopeKey("1", "300", OWNER),
                agent_id="bc-other-parent",
                owner_id=OWNER,
                thread_bound=True,
                parent_channel_id="999",
                name="elsewhere",
                active=True,
            )
        )
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(),
        )
        parent = MagicMock()
        parent.id = 100
        interaction = MagicMock()
        interaction.user = SimpleNamespace(id=int(OWNER), roles=[])
        interaction.guild_id = 1
        interaction.channel_id = 100
        interaction.channel = parent
        interaction.guild = SimpleNamespace(id=1)
        ctx = SimpleNamespace(interaction=interaction)
        seen = {}

        async def capture_ephemeral(_interaction, content):
            seen["content"] = content

        with patch_cursor(mod, "_gate", new=AsyncMock(return_value=True)):
            with patch_cursor(mod, "_channel_is_thread", return_value=False):
                with patch_cursor(mod, "_ephemeral", new=capture_ephemeral):
                    await mod.cursor_sessions(ctx)

        body = seen.get("content") or ""
        self.assertIn("bc-here", body)
        self.assertNotIn("bc-other-parent", body)
        self.assertIn("thread", body.lower())



class TestReplyChainSelfExclusion(unittest.IsolatedAsyncioTestCase):
    async def test_excludes_triggering_message_without_discord_reply(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        mod.reset_runtime(config=cfg)
        message = MagicMock()
        message.id = 10
        message.content = "please do the thing"
        message.attachments = []
        message.guild = SimpleNamespace(id=1)
        message.channel = SimpleNamespace(id=200)
        message.author = SimpleNamespace(name="owner")
        message.reference = None
        seen = []

        async def fake_chain(target, max_length=-1, include_message=False):
            seen.append(("text", target is message, include_message))
            return [("ancestor", "older")] if include_message else None

        async def fake_msg_chain(target, max_length=-1, include_message=False):
            seen.append(("msg", target is message, include_message))
            return [target] if include_message else []

        with patch_cursor(mod, "get_reference_chain", new=fake_chain):
            with patch_cursor(mod, "get_reference_message_chain", new=fake_msg_chain):
                with patch_cursor(mod, "collect_chain_attachments", return_value=[]):
                    text_out, images, skipped = await mod._build_context_from_message(
                        message, "please do the thing"
                    )
        self.assertEqual(seen, [("text", True, False), ("msg", True, False)])
        self.assertNotIn("Reply chain", text_out)
        self.assertIn("please do the thing", text_out)

    async def test_includes_fetched_ref_target(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        mod.reset_runtime(config=cfg)
        message = MagicMock()
        message.id = 10
        message.content = "follow up"
        message.attachments = []
        message.guild = SimpleNamespace(id=1, get_channel=MagicMock(return_value=None))
        message.channel = MagicMock()
        message.channel.id = 200
        message.author = SimpleNamespace(name="owner")
        message.reference = None
        target = MagicMock()
        target.id = 99
        target.content = "original context"
        target.author = SimpleNamespace(name="someone")
        target.reference = None
        message.channel.fetch_message = AsyncMock(return_value=target)
        seen = []

        async def fake_chain(tgt, max_length=-1, include_message=False):
            seen.append(("text", tgt is target, include_message))
            return [("someone", "original context")] if include_message else None

        async def fake_msg_chain(tgt, max_length=-1, include_message=False):
            seen.append(("msg", tgt is target, include_message))
            return [tgt] if include_message else []

        with patch_cursor(mod, "get_reference_chain", new=fake_chain):
            with patch_cursor(mod, "get_reference_message_chain", new=fake_msg_chain):
                with patch_cursor(mod, "collect_chain_attachments", return_value=[]):
                    with patch_cursor(
                        mod,
                        "parse_message_reference",
                        return_value=(200, 99),
                    ):
                        text_out, images, skipped = await mod._build_context_from_message(
                            message,
                            "follow up",
                            message_ref="99",
                        )
        self.assertEqual(seen, [("text", True, True), ("msg", True, True)])
        self.assertIn("Reply chain", text_out)
        self.assertIn("original context", text_out)


class TestTranslateGuidelines(unittest.TestCase):
    def test_tables_guideline_present(self):
        mod = load_cursor_plugin()
        text = mod.discord_ui.TRANSLATE_GUIDELINES
        self.assertIn("Discord does not render markdown tables", text)
        self.assertIn("triple-backtick code blocks", text)


if __name__ == "__main__":
    unittest.main()
