import asyncio
import json
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.client import CursorCloudClient, parse_sse_chunk
from cursor_cloud.config import load_cursor_config
from cursor_cloud.errors import (
    AuthenticationError,
    BusyRunError,
    RateLimitError,
    StreamExpiredError,
    ValidationError,
)
from cursor_cloud.models import StreamEvent


def make_config(**overrides):
    env = {"CURSOR_API_KEY": "test-key", "GOD": "123456789012345678"}
    plugin = {
        "enabled": True,
        "default_repository_url": "https://github.com/org/repo",
        **overrides,
    }
    return load_cursor_config(plugin, env=env)


class TestParseSSE(unittest.TestCase):
    def test_multiline_data_and_id(self):
        buf = (
            "id: 1-0\n"
            "event: assistant\n"
            'data: {"text":"hello"}\n'
            "\n"
            "event: heartbeat\n"
            "data: {}\n"
            "\n"
            "partial"
        )
        events, rem = parse_sse_chunk(buf)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].event, "assistant")
        self.assertEqual(events[0].id, "1-0")
        self.assertEqual(events[0].data["text"], "hello")
        self.assertEqual(events[1].event, "heartbeat")
        self.assertEqual(rem, "partial")

    def test_status_without_id(self):
        events, _ = parse_sse_chunk(
            'event: status\ndata: {"runId":"r1","status":"RUNNING"}\n\n'
        )
        self.assertEqual(events[0].id, None)
        self.assertEqual(events[0].data["status"], "RUNNING")


class TestCursorClient(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cfg = make_config()
        self.http = AsyncMock()
        self.client = CursorCloudClient(self.cfg, client=self.http)

    def _resp(self, status, body, headers=None):
        resp = MagicMock()
        resp.status_code = status
        resp.headers = headers or {}
        resp.json.return_value = body
        resp.text = json.dumps(body)
        resp.aclose = AsyncMock()
        resp.aread = AsyncMock()
        return resp

    async def test_basic_auth_and_create_agent_payload(self):
        self.http.request = AsyncMock(
            return_value=self._resp(
                200,
                {
                    "agent": {
                        "id": "bc-1",
                        "name": "n",
                        "status": "ACTIVE",
                        "latestRunId": "run-1",
                    },
                    "run": {
                        "id": "run-1",
                        "agentId": "bc-1",
                        "status": "CREATING",
                    },
                },
            )
        )
        # Ensure client uses our mock as already provided
        agent, run = await self.client.create_agent(
            "do thing",
            model="composer-2",
            images=[{"url": "https://cdn.example/a.png"}],
        )
        self.assertEqual(agent.id, "bc-1")
        self.assertEqual(run.id, "run-1")
        kwargs = self.http.request.await_args.kwargs
        body = kwargs["json"]
        self.assertEqual(body["prompt"]["text"], "do thing")
        self.assertEqual(body["model"]["id"], "composer-2")
        self.assertEqual(body["repos"][0]["url"], "https://github.com/org/repo")
        self.assertIn("images", body["prompt"])

    async def test_follow_up_has_no_model_field(self):
        self.http.request = AsyncMock(
            return_value=self._resp(
                200,
                {"run": {"id": "run-2", "agentId": "bc-1", "status": "CREATING"}},
            )
        )
        await self.client.create_run("bc-1", "follow up")
        body = self.http.request.await_args.kwargs["json"]
        self.assertNotIn("model", body)
        self.assertEqual(body["prompt"]["text"], "follow up")

    async def test_busy_conflict(self):
        self.http.request = AsyncMock(
            return_value=self._resp(
                409, {"code": "agent_busy", "message": "busy"}
            )
        )
        with self.assertRaises(BusyRunError):
            await self.client.create_run("bc-1", "x")

    async def test_auth_error(self):
        self.http.request = AsyncMock(
            return_value=self._resp(401, {"message": "nope"})
        )
        with self.assertRaises(AuthenticationError):
            await self.client.list_models()

    async def test_rate_limit_honors_retry_after_on_idempotent(self):
        limited = self._resp(429, {"message": "slow"}, headers={"Retry-After": "0"})
        ok = self._resp(200, {"items": [{"id": "m1", "displayName": "M"}]})
        self.http.request = AsyncMock(side_effect=[limited, ok])
        models = await self.client.list_models()
        self.assertEqual(models[0].id, "m1")
        self.assertEqual(self.http.request.await_count, 2)

    async def test_stream_410_fallback(self):
        # First stream request raises via status mapping
        expired = self._resp(410, {"code": "stream_expired", "message": "gone"})
        expired.aread = AsyncMock()
        self.http.build_request = MagicMock(return_value=MagicMock())
        self.http.send = AsyncMock(return_value=expired)
        self.http.request = AsyncMock(
            return_value=self._resp(
                200,
                {
                    "id": "run-1",
                    "agentId": "bc-1",
                    "status": "FINISHED",
                    "result": "done",
                    "durationMs": 10,
                },
            )
        )
        events = []
        async for ev in self.client.stream_run_with_fallback("bc-1", "run-1"):
            events.append(ev)
        self.assertEqual(events[0].event, "result")
        self.assertEqual(events[0].data["text"], "done")
        self.assertEqual(events[-1].event, "done")

    async def test_cancel_not_retried_as_mutation(self):
        self.http.request = AsyncMock(
            return_value=self._resp(500, {"message": "boom"})
        )
        with self.assertRaises(Exception):
            await self.client.cancel_run("bc-1", "run-1")
        self.assertEqual(self.http.request.await_count, 1)

    async def test_list_agents_pagination_cursor(self):
        self.http.request = AsyncMock(
            return_value=self._resp(
                200,
                {
                    "items": [{"id": "bc-1", "name": "a", "status": "ACTIVE"}],
                    "nextCursor": "next",
                },
            )
        )
        items, cursor = await self.client.list_agents(limit=10, cursor="prev")
        self.assertEqual(cursor, "next")
        self.assertEqual(items[0].id, "bc-1")
        params = self.http.request.await_args.kwargs["params"]
        self.assertEqual(params["cursor"], "prev")

    async def test_stream_timeout_uses_configured_stream_read(self):
        cfg = make_config(stream_timeout_seconds=123.0, read_timeout_seconds=30.0)
        client = CursorCloudClient(cfg, client=self.http)
        timeout = client._stream_timeout()
        self.assertEqual(timeout.read, 123.0)
        self.assertEqual(timeout.connect, cfg.connect_timeout_seconds)
        # Non-stream path keeps shorter read timeout on the shared client config.
        self.assertEqual(cfg.read_timeout_seconds, 30.0)
        self.assertNotEqual(cfg.read_timeout_seconds, cfg.stream_timeout_seconds)

    async def test_stream_run_passes_stream_timeout_to_send(self):
        cfg = make_config(stream_timeout_seconds=456.0, read_timeout_seconds=30.0)
        http = AsyncMock()
        client = CursorCloudClient(cfg, client=http)
        seen = {}

        class StreamResp:
            status_code = 200
            headers = {}

            async def aread(self):
                return b""

            async def aclose(self):
                return None

            async def aiter_text(self):
                if False:
                    yield ""

        req = MagicMock()

        def build_request(*args, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            return req

        http.build_request = MagicMock(side_effect=build_request)
        http.send = AsyncMock(return_value=StreamResp())

        events = []
        async for ev in client.stream_run("bc-1", "run-1"):
            events.append(ev)
        self.assertEqual(seen["timeout"].read, 456.0)
        http.send.assert_awaited()
        self.assertTrue(http.send.await_args.kwargs.get("stream"))

    async def test_create_agent_resolves_run_via_get_agent(self):
        create = self._resp(
            200,
            {"agent": {"id": "bc-1", "name": "n", "status": "ACTIVE"}},
        )
        refresh = self._resp(
            200,
            {
                "id": "bc-1",
                "name": "n",
                "status": "ACTIVE",
                "latestRunId": "run-resolved",
            },
        )
        self.http.request = AsyncMock(side_effect=[create, refresh])
        agent, run = await self.client.create_agent("do thing")
        self.assertEqual(agent.id, "bc-1")
        self.assertEqual(run.id, "run-resolved")
        self.assertEqual(self.http.request.await_count, 2)

    async def test_create_agent_missing_run_id_raises(self):
        self.http.request = AsyncMock(
            side_effect=[
                self._resp(200, {"agent": {"id": "bc-1", "status": "ACTIVE"}}),
                self._resp(200, {"id": "bc-1", "status": "ACTIVE"}),
            ]
        )
        with self.assertRaises(ValidationError) as ctx:
            await self.client.create_agent("do thing")
        self.assertEqual(ctx.exception.code, "missing_run_id")

    async def test_get_run_retries_not_found(self):
        missing = self._resp(404, {"message": "Run not found"})
        ok = self._resp(
            200,
            {"id": "run-1", "agentId": "bc-1", "status": "RUNNING"},
        )
        self.http.request = AsyncMock(side_effect=[missing, ok])
        with patch("cursor_cloud.client.asyncio.sleep", new=AsyncMock()):
            run = await self.client.get_run("bc-1", "run-1", retries=2, retry_delay_s=0)
        self.assertEqual(run.id, "run-1")
        self.assertEqual(self.http.request.await_count, 2)

    async def test_get_run_empty_id_raises(self):
        with self.assertRaises(ValidationError):
            await self.client.get_run("bc-1", "")


class TestReferenceFetchResilience(unittest.IsolatedAsyncioTestCase):
    async def test_get_next_reference_deleted_message_returns_none(self):
        import discord

        from modules.utils import get_next_reference, get_reference_message, references

        references.clear()
        channel = MagicMock()
        channel.fetch_message = AsyncMock(
            side_effect=discord.NotFound(MagicMock(), {"code": 10008})
        )
        message = MagicMock()
        message.id = 101
        message.author = SimpleNamespace(name="user")
        message.content = "$agent hello"
        message.reference = SimpleNamespace(message_id=999)
        message.channel = channel

        self.assertIsNone(await get_next_reference(message))
        # Failed fetch is remembered so we do not keep hitting Discord.
        self.assertIsNone(await get_reference_message(message))
        channel.fetch_message.assert_awaited_once_with(999)


if __name__ == "__main__":
    unittest.main()
