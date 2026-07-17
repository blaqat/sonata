"""Production close path must invoke Cursor cleanup (py-cord has no on_close)."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_cursor_plugin():
    from modules.AI_manager import AI_Manager

    path = ROOT / "src" / "modules" / "plugins" / "cursor-commands.py"
    spec = importlib.util.spec_from_file_location("cursor_commands_close", path)
    module = importlib.util.module_from_spec(spec)
    previous = AI_Manager.M.MANAGER
    try:
        spec.loader.exec_module(module)
    finally:
        AI_Manager.M.MANAGER = previous
    return module


class TestSonataClientClosePath(unittest.IsolatedAsyncioTestCase):
    async def test_close_invokes_cleanup_cancels_tasks_closes_http(self):
        mod = load_cursor_plugin()

        # Minimal stand-in for SonataClient.close override logic.
        class FakeBot:
            def __init__(self):
                self._sonata_cursor_cleanup_done = False
                self._cursor_cleanup = mod.cleanup_cursor_runtime
                self.super_close = AsyncMock()

            async def close(self):
                if not self._sonata_cursor_cleanup_done:
                    self._sonata_cursor_cleanup_done = True
                    cleanup = getattr(self, "_cursor_cleanup", None)
                    if callable(cleanup):
                        result = cleanup()
                        if asyncio.iscoroutine(result):
                            await result
                await self.super_close()

        async def _hang():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise

        expiry = asyncio.create_task(_hang())
        reconcile = asyncio.create_task(_hang())
        tracker = asyncio.create_task(_hang())
        client = MagicMock()
        client.aclose = AsyncMock()
        cdn = MagicMock()
        cdn.aclose = AsyncMock()
        mod._STATE.update(
            {
                "_cleanup_done": False,
                "expiry_task": expiry,
                "reconcile_task": reconcile,
                "trackers": {"a1": tracker},
                "client": client,
                "cdn": cdn,
            }
        )

        bot = FakeBot()
        await bot.close()
        await bot.close()  # idempotent — second close must not double-clean

        self.assertTrue(expiry.cancelled() or expiry.done())
        self.assertTrue(reconcile.cancelled() or reconcile.done())
        self.assertTrue(tracker.cancelled() or tracker.done())
        client.aclose.assert_awaited_once()
        cdn.aclose.assert_awaited_once()
        self.assertEqual(bot.super_close.await_count, 2)

    async def test_index_sonata_client_close_wires_cleanup(self):
        """Import SonataClient.close source contract without full bot boot."""
        index_path = ROOT / "src" / "index.py"
        text = index_path.read_text()
        self.assertIn("async def close(self)", text)
        self.assertIn("_cursor_cleanup", text)
        self.assertIn("await super().close()", text)
        self.assertNotIn('@bot.listen("on_close")', text)


if __name__ == "__main__":
    unittest.main()
