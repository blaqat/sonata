import asyncio
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.models import (
    RunRecord,
    RunSnapshot,
    RunStatus,
    ScopeKey,
    StreamEvent,
    ToolActivity,
)
from cursor_cloud.run_log import MemoryRunLogStore, format_history_message
from cursor_cloud.run_tracker import MemoryStatusSink, RunTracker, is_stream_unavailable_error
from cursor_cloud.status_renderer import (
    format_live_peek,
    initial_queued_message,
    redact_untrusted,
    render_status,
    tool_family,
)
from cursor_cloud.thread_renderer import render_thread_summary
from cursor_cloud.thread_sink import ThreadActivitySink


class TestRenderer(unittest.TestCase):
    def test_h3_only_and_limit(self):
        snap = RunSnapshot(
            run_id="run-1",
            agent_id="bc-1",
            status=RunStatus.FINISHED,
            result_text="# secret\n" + ("x" * 3000),
            tools=[
                ToolActivity("c1", "read_file", "completed", "keys=path"),
                ToolActivity("c2", "shell", "running", "keys=command"),
            ],
        )
        text = render_status(snap, agent_name="Agent")
        self.assertTrue(text.startswith("### "))
        self.assertNotRegex(text, r"(?m)^##\s")
        self.assertNotRegex(text, r"(?m)^#\s")
        self.assertLessEqual(len(text), 2000)
        self.assertIn("…(truncated)", text)
        self.assertNotIn("@everyone", redact_untrusted("hi @everyone"))

    def test_initial_queued(self):
        msg = initial_queued_message()
        self.assertTrue(msg.startswith("### Queued"))

    def test_thinking_peek_while_running(self):
        snap = RunSnapshot(
            run_id="r",
            agent_id="a",
            status=RunStatus.RUNNING,
            thinking_text="considering the file layout carefully",
        )
        text = render_status(snap)
        self.assertIn("Thinking", text)
        self.assertIn("file layout", text)

    def test_format_live_peek_head_and_tail_with_sentence_breaks(self):
        short = "short thought"
        self.assertEqual(format_live_peek(short, head_chars=20, tail_chars=20), short)

        head = "First I will inspect the auth module carefully. "
        middle = ("Then there is a long bridge of filler words that we do not need "
                  "to show in the live Discord peek because it is just transitional "
                  "reasoning without a useful thesis or conclusion. ") * 4
        tail = "Finally I will propose a concrete patch for the idle session path."
        text = head + middle + tail
        peek = format_live_peek(text, head_chars=80, tail_chars=90)
        self.assertIn("…", peek)
        self.assertTrue(peek.startswith("First I will inspect"))
        self.assertIn("concrete patch for the idle session path", peek)
        # Prefer sentence boundaries over mid-word cuts near the join.
        before, _, after = peek.partition("…")
        self.assertTrue(before.rstrip().endswith(".") or before.rstrip().endswith("."))
        self.assertTrue(after.lstrip()[0].isupper() or after.lstrip().startswith("Finally"))

    def test_thinking_peek_preserves_opening_and_latest(self):
        opening = "I am starting by mapping how image URLs enter chat history. "
        filler = ("This is transitional analysis that goes on for a while and should "
                  "be elided from the live peek so the opening and ending stay visible. ") * 8
        ending = "So the ispy plugin batches four images into Gemini flash."
        snap = RunSnapshot(
            run_id="r",
            agent_id="a",
            status=RunStatus.RUNNING,
            thinking_text=opening + filler + ending,
        )
        text = render_status(snap)
        self.assertIn("mapping how image URLs", text)
        self.assertIn("ispy plugin batches", text)
        self.assertIn("…", text)

    def test_finished_does_not_show_stale_error(self):
        snap = RunSnapshot(
            run_id="r",
            agent_id="a",
            status=RunStatus.FINISHED,
            result_text="all good",
            error_message="Run stream is no longer available",
        )
        text = render_status(snap)
        self.assertTrue(text.startswith("### Finished"))
        self.assertNotIn("### Error", text)
        self.assertIn("all good", text)


class TestStreamUnavailable(unittest.TestCase):
    def test_detects_message_and_code(self):
        self.assertTrue(
            is_stream_unavailable_error(
                {"message": "Run stream is no longer available"}
            )
        )
        self.assertTrue(is_stream_unavailable_error({"code": "stream_expired"}))
        self.assertFalse(is_stream_unavailable_error({"message": "tool failed"}))


class TestTracker(unittest.IsolatedAsyncioTestCase):
    async def test_coalesce_and_terminal_flush(self):
        class FakeClient:
            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent("status", {"runId": "r1", "status": "RUNNING"})
                yield StreamEvent("assistant", {"text": "hi"}, id="1")
                yield StreamEvent("heartbeat", {})
                yield StreamEvent(
                    "result",
                    {"runId": "r1", "status": "FINISHED", "text": "done", "durationMs": 5},
                    id="2",
                )
                yield StreamEvent("done", {})

        sink = MemoryStatusSink()
        tracker = RunTracker(FakeClient(), sink, edit_interval_ms=10_000)
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertTrue(any(terminal for _, terminal in sink.updates))
        self.assertTrue(sink.updates[0][0].startswith("### "))
        # heartbeat should not be required for activity callback
        called = []

        async def on_act(name):
            called.append(name)

        sink2 = MemoryStatusSink()
        tracker2 = RunTracker(
            FakeClient(), sink2, edit_interval_ms=10_000, on_meaningful_activity=on_act
        )
        await tracker2.track("bc", "r1")
        self.assertIn("assistant", called)
        self.assertIn("result", called)
        self.assertNotIn("heartbeat", called)

    async def test_tool_redaction_no_secret_values(self):
        tracker = RunTracker(None, MemoryStatusSink())
        snap = RunSnapshot(run_id="r", agent_id="a")
        tracker.apply_event(
            snap,
            StreamEvent(
                "tool_call",
                {
                    "callId": "1",
                    "name": "shell",
                    "status": "completed",
                    "args": {"command": "export KEY=secret"},
                    "result": {"out": "secret"},
                },
            ),
        )
        summary = snap.tools[0].summary
        self.assertNotIn("secret", summary)
        self.assertIn("keys=", summary)

    async def test_family_counts_survive_tool_cap(self):
        tracker = RunTracker(None, MemoryStatusSink())
        snap = RunSnapshot(run_id="r", agent_id="a")
        for i in range(15):
            tracker.apply_event(
                snap,
                StreamEvent(
                    "tool_call",
                    {
                        "callId": f"c{i}",
                        "name": "grep",
                        "status": "completed",
                        "args": {"pattern": f"p{i}"},
                    },
                ),
            )
        self.assertEqual(len(snap.tools), 12)
        self.assertEqual(snap.tool_family_counts.get("search"), 15)

    async def test_task_label_whitelist_and_non_task_secrecy(self):
        tracker = RunTracker(None, MemoryStatusSink())
        snap = RunSnapshot(run_id="r", agent_id="a")
        tracker.apply_event(
            snap,
            StreamEvent(
                "tool_call",
                {
                    "callId": "task-1",
                    "name": "Task",
                    "status": "completed",
                    "args": {
                        "description": "Inventory API credentials",
                        "secret": "should-not-appear",
                    },
                },
            ),
        )
        tracker.apply_event(
            snap,
            StreamEvent(
                "tool_call",
                {
                    "callId": "shell-1",
                    "name": "Shell",
                    "status": "completed",
                    "args": {
                        "command": "cat /etc/passwd",
                        "description": "must not become shell label",
                    },
                },
            ),
        )
        tracker.apply_event(
            snap,
            StreamEvent(
                "tool_call",
                {
                    "callId": "task-2",
                    "name": "Task",
                    "status": "running",
                    "args": {"prompt": "ignored non-whitelist"},
                },
            ),
        )
        self.assertEqual(len(snap.subagents), 2)
        self.assertEqual(snap.subagents[0].label, "Inventory API credentials")
        self.assertEqual(snap.subagents[1].label, "Subagent 2")
        self.assertNotIn("should-not-appear", snap.subagents[0].summary)
        self.assertNotIn("should-not-appear", snap.subagents[0].label)
        shell = next(t for t in snap.tools if t.call_id == "shell-1")
        self.assertNotIn("cat /etc/passwd", shell.summary)
        self.assertNotIn("must not become", shell.summary)
        self.assertIn("keys=", shell.summary)
        self.assertEqual(snap.tool_family_counts.get("subagent"), 2)
        self.assertEqual(snap.tool_family_counts.get("shell"), 1)

    async def test_thinking_seconds_from_monotonic_timer(self):
        tracker = RunTracker(None, MemoryStatusSink())
        snap = RunSnapshot(run_id="r", agent_id="a")
        tracker.apply_event(snap, StreamEvent("thinking", {"text": "hmm"}))
        self.assertIsNone(snap.thinking_seconds)
        tracker.apply_event(snap, StreamEvent("assistant", {"text": "ok"}))
        self.assertIsNotNone(snap.thinking_seconds)
        self.assertGreaterEqual(snap.thinking_seconds, 0.0)

    async def test_snapshot_serialization_compat_for_new_fields(self):
        snap = RunSnapshot(
            run_id="r",
            agent_id="a",
            tool_family_counts={"search": 2},
            subagents=[ToolActivity("t1", "Task", "completed", label="L")],
            thinking_seconds=1.5,
        )
        data = snap.to_dict()
        restored = RunSnapshot.from_dict(data)
        self.assertEqual(restored.tool_family_counts, {"search": 2})
        self.assertEqual(restored.subagents[0].label, "L")
        self.assertEqual(restored.thinking_seconds, 1.5)
        legacy = RunSnapshot.from_dict({"run_id": "r", "agent_id": "a"})
        self.assertEqual(legacy.tool_family_counts, {})
        self.assertEqual(legacy.subagents, [])
        self.assertIsNone(legacy.thinking_seconds)

    async def test_sse_stream_expired_reconciles_to_finished(self):
        class FakeClient:
            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent("status", {"runId": "r1", "status": "RUNNING"})
                yield StreamEvent("thinking", {"text": "working on it"})
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "t1",
                        "name": "readFile",
                        "status": "completed",
                        "args": {"path": "/tmp/x"},
                    },
                )
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_expired",
                        "message": "Run stream is no longer available",
                    },
                )

            async def get_run(self, agent_id, run_id):
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="shipped successfully",
                    duration_ms=1234,
                )

        scope = ScopeKey("1", "2", "3")
        logs = MemoryRunLogStore()
        sink = MemoryStatusSink()
        tracker = RunTracker(
            FakeClient(),
            sink,
            edit_interval_ms=10_000,
            run_log=logs,
            scope=scope,
            poll_interval_s=0.01,
        )
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(snap.result_text, "shipped successfully")
        self.assertEqual(snap.error_message, "")
        final = sink.updates[-1][0]
        self.assertTrue(final.startswith("### Finished"))
        self.assertIn("shipped successfully", final)
        self.assertNotIn("### Error", final)
        self.assertNotIn("no longer available", final)

        entries = await logs.get_entries(scope, "r1", limit=50)
        kinds = [e.kind for e in entries]
        self.assertIn("tool_call", kinds)
        self.assertIn("thinking", kinds)
        self.assertIn("result", kinds)
        self.assertNotIn("status", kinds)
        self.assertNotIn("system", kinds)

    async def test_stream_unavailable_while_running_polls_until_finished(self):
        """Regression: stream drop while RUNNING must not freeze status on Running."""

        class FakeClient:
            def __init__(self):
                self.polls = 0

            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent("status", {"runId": "r1", "status": "CREATING"})
                yield StreamEvent("status", {"runId": "r1", "status": "RUNNING"})
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_expired",
                        "message": "Run stream is no longer available",
                    },
                )

            async def get_run(self, agent_id, run_id):
                self.polls += 1
                if self.polls < 3:
                    return RunRecord(
                        id=run_id,
                        agent_id=agent_id,
                        status=RunStatus.RUNNING,
                    )
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="final from poll",
                    duration_ms=50,
                )

        scope = ScopeKey("1", "2", "3")
        logs = MemoryRunLogStore()
        sink = MemoryStatusSink()
        client = FakeClient()
        tracker = RunTracker(
            client,
            sink,
            edit_interval_ms=10_000,
            run_log=logs,
            scope=scope,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(snap.result_text, "final from poll")
        self.assertGreaterEqual(client.polls, 3)
        final = sink.updates[-1][0]
        self.assertTrue(final.startswith("### Finished"))
        self.assertIn("final from poll", final)
        # Intermediate Running updates should not have been terminal.
        non_terminal_running = [
            content for content, terminal in sink.updates if (not terminal and "Running" in content)
        ]
        self.assertTrue(non_terminal_running)

        entries = await logs.get_entries(scope, "r1", limit=50, kinds=None)
        kinds = [e.kind for e in entries]
        self.assertIn("result", kinds)
        self.assertEqual(kinds.count("result"), 1)
        self.assertNotIn("status", kinds)
        self.assertNotIn("system", kinds)
        focused = await logs.get_entries(
            scope, "r1", limit=50, kinds={"prompt", "thinking", "tool_call", "assistant", "result", "error"}
        )
        self.assertEqual([e.kind for e in focused], ["result"])

    async def test_stream_exit_non_terminal_polls_get_run(self):
        class FakeClient:
            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent("status", {"runId": "r1", "status": "RUNNING"})
                # iterator ends without result/done

            async def get_run(self, agent_id, run_id):
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="polled result",
                )

        sink = MemoryStatusSink()
        tracker = RunTracker(
            FakeClient(),
            sink,
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
        )
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertIn("polled result", sink.updates[-1][0])

    async def test_stream_unavailable_reconcile_miss_then_poll_recovers(self):
        """Follow-up race: first GET after stream drop fails; later polls succeed."""
        from cursor_cloud.errors import AgentRunError

        class FakeClient:
            def __init__(self):
                self.polls = 0

            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent("status", {"runId": "r1", "status": "RUNNING"})
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_unavailable",
                        "message": "Run stream is no longer available",
                    },
                )

            async def get_run(self, agent_id, run_id):
                self.polls += 1
                if self.polls == 1:
                    raise AgentRunError(
                        "Run stream is no longer available",
                        code="stream_unavailable",
                    )
                if self.polls < 4:
                    return RunRecord(
                        id=run_id,
                        agent_id=agent_id,
                        status=RunStatus.RUNNING,
                    )
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="recovered after race",
                )

        sink = MemoryStatusSink()
        tracker = RunTracker(
            FakeClient(),
            sink,
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(snap.result_text, "recovered after race")
        self.assertNotIn("no longer available", sink.updates[-1][0])

    async def test_stream_open_cloud_error_unavailable_polls(self):
        """Stream open failure with stream-unavailable message must poll, not ERROR."""
        from cursor_cloud.errors import AgentRunError

        class FakeClient:
            def __init__(self):
                self.polls = 0

            async def stream_run_with_fallback(self, *a, **k):
                raise AgentRunError(
                    "Run stream is no longer available",
                    code="stream_unavailable",
                )
                yield  # make this an async generator  # noqa: RET503

            async def get_run(self, agent_id, run_id):
                self.polls += 1
                if self.polls < 2:
                    return RunRecord(
                        id=run_id,
                        agent_id=agent_id,
                        status=RunStatus.RUNNING,
                    )
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="from poll after open fail",
                )

        sink = MemoryStatusSink()
        tracker = RunTracker(
            FakeClient(),
            sink,
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertIn("from poll after open fail", snap.result_text)

    async def test_mcp_tool_family_from_name_and_args(self):
        self.assertEqual(tool_family("mcp"), "mcp")
        self.assertEqual(
            tool_family("mcp", {"toolName": "search", "serverName": "notion"}),
            "mcp:search",
        )
        self.assertEqual(
            tool_family("mcp", {"tool_name": "fetch", "server": "plugin-notion"}),
            "mcp:fetch",
        )
        self.assertEqual(
            tool_family("mcp__plugin-notion-workspace-notion__search"),
            "mcp:search",
        )
        self.assertEqual(tool_family("CallMcpTool", {"name": "notion-search"}), "mcp:notion-search")
        self.assertEqual(tool_family("read_file"), "read")
        self.assertEqual(tool_family("run_terminal_cmd"), "shell")

        tracker = RunTracker(None, MemoryStatusSink())
        snap = RunSnapshot(run_id="r", agent_id="a")
        tracker.apply_event(
            snap,
            StreamEvent(
                "tool_call",
                {
                    "callId": "m1",
                    "name": "mcp",
                    "status": "completed",
                    "args": {
                        "toolName": "search",
                        "serverName": "notion",
                        "query": "SONA-105 secret-should-not-leak",
                    },
                },
            ),
        )
        tracker.apply_event(
            snap,
            StreamEvent(
                "tool_call",
                {
                    "callId": "m2",
                    "name": "mcp",
                    "status": "completed",
                    "args": {"toolName": "fetch", "serverName": "notion"},
                },
            ),
        )
        self.assertEqual(snap.tool_family_counts.get("mcp:search"), 1)
        self.assertEqual(snap.tool_family_counts.get("mcp:fetch"), 1)
        summary = render_thread_summary(snap)
        self.assertIn("`mcp:search` ×1", summary)
        self.assertIn("`mcp:fetch` ×1", summary)
        self.assertNotIn("secret-should-not-leak", snap.tools[0].summary)
        self.assertIn("tool=search", snap.tools[0].summary)

    async def test_followup_stream_race_resume_recovers_tools(self):
        """Follow-up: first SSE unavailable, later resume delivers thinking/tools/MCP."""

        class FakeClient:
            def __init__(self):
                self.polls = 0
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
                yield StreamEvent("status", {"runId": "r2", "status": "RUNNING"}, id="1")
                yield StreamEvent("thinking", {"text": "checking notion"}, id="2")
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "t1",
                        "name": "mcp",
                        "status": "completed",
                        "args": {"toolName": "search", "serverName": "notion"},
                    },
                    id="3",
                )
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "t2",
                        "name": "grep",
                        "status": "completed",
                        "args": {"pattern": "x"},
                    },
                    id="4",
                )
                yield StreamEvent(
                    "result",
                    {
                        "runId": "r2",
                        "status": "FINISHED",
                        "text": "follow-up answer",
                        "durationMs": 50,
                    },
                    id="5",
                )
                yield StreamEvent("done", {}, id="6")

            async def get_run(self, agent_id, run_id):
                self.polls += 1
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
                    result="follow-up answer",
                    duration_ms=50,
                )

        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        sink = ThreadActivitySink(channel, activity, edit_interval_ms=0)
        tracker = RunTracker(
            FakeClient(),
            sink,
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        snap = await tracker.track("bc", "r2", initial_status=RunStatus.CREATING)
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(snap.tool_family_counts.get("mcp:search"), 1)
        self.assertEqual(snap.tool_family_counts.get("search"), 1)
        self.assertIsNotNone(snap.thinking_seconds)
        edited = (
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0]
        )
        self.assertIn("Thought for", edited)
        self.assertIn("`mcp:search` ×1", edited)
        self.assertIn("🔍 `search` ×1", edited)
        self.assertEqual(channel.send.await_args.args[0], "follow-up answer")
        self.assertEqual(channel.send.await_count, 1)

    async def test_get_finished_catchup_recovers_tools_once(self):
        """GET can finish first; bounded catch-up still recovers tool/thinking SSE."""

        class FakeClient:
            def __init__(self):
                self.polls = 0
                self.stream_attempts = 0
                self.resume_last_event_ids: list[str | None] = []

            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_unavailable",
                        "message": "Run stream is no longer available",
                    },
                )

            async def stream_run(self, agent_id, run_id, *, last_event_id=None):
                del agent_id, run_id
                self.stream_attempts += 1
                self.resume_last_event_ids.append(last_event_id)
                if self.polls < 2:
                    from cursor_cloud.errors import AgentRunError

                    raise AgentRunError(
                        "Run stream is no longer available",
                        code="stream_unavailable",
                    )
                yield StreamEvent("thinking", {"text": "catch up"}, id="10")
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "c1",
                        "name": "mcp",
                        "status": "completed",
                        "args": {"toolName": "fetch", "serverName": "notion"},
                    },
                    id="11",
                )
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "c1",
                        "name": "mcp",
                        "status": "completed",
                        "args": {"toolName": "fetch", "serverName": "notion"},
                    },
                    id="11",
                )
                yield StreamEvent(
                    "result",
                    {
                        "runId": "r2",
                        "status": "FINISHED",
                        "text": "caught up",
                    },
                    id="12",
                )
                yield StreamEvent("done", {}, id="13")

            async def get_run(self, agent_id, run_id):
                self.polls += 1
                if self.polls < 2:
                    return RunRecord(
                        id=run_id,
                        agent_id=agent_id,
                        status=RunStatus.RUNNING,
                    )
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="caught up",
                )

        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        client = FakeClient()
        tracker = RunTracker(
            client,
            ThreadActivitySink(channel, activity, edit_interval_ms=0),
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        snap = await tracker.track("bc", "r2")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(snap.tool_family_counts.get("mcp:fetch"), 1)
        self.assertEqual(channel.send.await_count, 1)
        self.assertEqual(channel.send.await_args.args[0], "caught up")
        edited = (
            activity.edit.await_args.kwargs.get("content")
            or activity.edit.await_args.args[0]
        )
        self.assertIn("`mcp:fetch` ×1", edited)
        self.assertIn("Thought for", edited)

    async def test_catchup_timeout_still_emits_terminal_answer(self):
        """Hung SSE catch-up must not suppress the already-known final answer."""
        import cursor_cloud.run_tracker as run_tracker_mod

        class FakeClient:
            def __init__(self):
                self.polls = 0

            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_unavailable",
                        "message": "Run stream is no longer available",
                    },
                )

            async def stream_run(self, *a, **k):
                await asyncio.sleep(30)
                if False:  # pragma: no cover - async generator
                    yield None

            async def get_run(self, agent_id, run_id):
                self.polls += 1
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.FINISHED,
                    result="answer without tools",
                )

        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        with patch.object(run_tracker_mod, "CATCHUP_RESUME_TIMEOUT_S", 0.05):
            tracker = RunTracker(
                FakeClient(),
                ThreadActivitySink(channel, activity, edit_interval_ms=0),
                edit_interval_ms=10_000,
                poll_interval_s=0.01,
                poll_max_s=2.0,
            )
            snap = await tracker.track("bc", "r2")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(channel.send.await_count, 1)
        self.assertEqual(channel.send.await_args.args[0], "answer without tools")

    async def test_resume_retries_without_invalid_last_event_id(self):
        from cursor_cloud.errors import ValidationError

        class FakeClient:
            def __init__(self):
                self.calls: list[str | None] = []

            async def stream_run_with_fallback(self, *a, **k):
                yield StreamEvent("status", {"runId": "r1", "status": "RUNNING"}, id="stale")
                yield StreamEvent(
                    "error",
                    {
                        "code": "stream_unavailable",
                        "message": "Run stream is no longer available",
                    },
                )

            async def stream_run(self, agent_id, run_id, *, last_event_id=None):
                del agent_id, run_id
                self.calls.append(last_event_id)
                if last_event_id == "stale":
                    raise ValidationError(
                        "invalid Last-Event-ID",
                        code="invalid_last_event",
                    )
                yield StreamEvent("thinking", {"text": "ok"}, id="1")
                yield StreamEvent(
                    "tool_call",
                    {
                        "callId": "t1",
                        "name": "Read",
                        "status": "completed",
                        "args": {"path": "a.py"},
                    },
                    id="2",
                )
                yield StreamEvent(
                    "result",
                    {"runId": "r1", "status": "FINISHED", "text": "ok"},
                    id="3",
                )
                yield StreamEvent("done", {}, id="4")

            async def get_run(self, agent_id, run_id):
                return RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status=RunStatus.RUNNING,
                )

        channel = MagicMock()
        channel.send = AsyncMock(return_value=SimpleNamespace(id=2))
        activity = MagicMock()
        activity.edit = AsyncMock()
        client = FakeClient()
        tracker = RunTracker(
            client,
            ThreadActivitySink(channel, activity, edit_interval_ms=0),
            edit_interval_ms=10_000,
            poll_interval_s=0.01,
            poll_max_s=2.0,
        )
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertEqual(snap.tool_family_counts.get("read"), 1)
        self.assertIn("stale", client.calls)
        self.assertIn(None, client.calls)
        self.assertEqual(channel.send.await_args.args[0], "ok")


class TestRunLog(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_retention_and_history_render(self):
        store = MemoryRunLogStore(max_runs_per_scope=2, max_entries_per_run=5)
        scope = ScopeKey("g", "c", "u")
        for rid in ("r1", "r2", "r3"):
            await store.append(
                scope, agent_id="a", run_id=rid, kind="prompt", summary=f"p-{rid}"
            )
        self.assertEqual(await store.list_run_ids(scope), ["r3", "r2"])
        self.assertEqual(await store.entry_count(scope, "r1"), 0)

        for i in range(8):
            await store.append(
                scope,
                agent_id="a",
                run_id="r3",
                kind="thinking",
                summary=f"thought-{i}",
            )
        self.assertEqual(await store.entry_count(scope, "r3"), 5)
        entries = await store.get_entries(scope, "r3", offset=0, limit=12)
        text = format_history_message(
            entries,
            run_id="r3",
            page=1,
            total_entries=5,
            page_size=12,
            agent_id="a",
        )
        self.assertTrue(text.startswith("### History"))
        self.assertIn("thinking", text)
        self.assertLessEqual(len(text), 2000)


if __name__ == "__main__":
    unittest.main()
