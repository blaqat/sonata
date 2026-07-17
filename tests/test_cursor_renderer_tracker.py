import pathlib
import sys
import unittest

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
    initial_queued_message,
    redact_untrusted,
    render_status,
)


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
        tracker = RunTracker(FakeClient(), sink, edit_interval_ms=10_000)
        snap = await tracker.track("bc", "r1")
        self.assertEqual(snap.status, RunStatus.FINISHED)
        self.assertIn("polled result", sink.updates[-1][0])


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
