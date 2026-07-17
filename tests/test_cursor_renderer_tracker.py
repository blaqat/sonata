import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.models import RunSnapshot, RunStatus, StreamEvent, ToolActivity
from cursor_cloud.run_tracker import MemoryStatusSink, RunTracker
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
            status=RunStatus.RUNNING,
            assistant_text="# secret\n" + ("x" * 3000),
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


if __name__ == "__main__":
    unittest.main()
