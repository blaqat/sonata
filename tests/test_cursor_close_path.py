"""Production close path must invoke Cursor cleanup (py-cord has no on_close)."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modules.cursor_shutdown import close_with_cursor_cleanup


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


class TestCloseWithCursorCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_production_close_helper_cancels_tasks_closes_http(self):
        """Exercise the same helper SonataClient.close uses (no full bot import)."""
        mod = load_cursor_plugin()

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

        bot = MagicMock()
        bot._sonata_cursor_cleanup_done = False
        bot._cursor_cleanup = mod.cleanup_cursor_runtime
        super_close = AsyncMock()

        await close_with_cursor_cleanup(bot, sonata=None, super_close=super_close)
        await close_with_cursor_cleanup(bot, sonata=None, super_close=super_close)

        self.assertTrue(bot._sonata_cursor_cleanup_done)
        self.assertTrue(expiry.cancelled() or expiry.done())
        self.assertTrue(reconcile.cancelled() or reconcile.done())
        self.assertTrue(tracker.cancelled() or tracker.done())
        client.aclose.assert_awaited_once()
        cdn.aclose.assert_awaited_once()
        self.assertEqual(super_close.await_count, 2)

    async def test_close_resolves_sonata_cursor_cleanup(self):
        cursor = MagicMock()
        cursor.cleanup = AsyncMock()
        sonata = MagicMock()
        sonata.cursor = cursor
        sonata.get = MagicMock(return_value=None)
        bot = MagicMock()
        bot._sonata_cursor_cleanup_done = False
        # No bot._cursor_cleanup — fall through to sonata.cursor.cleanup
        if hasattr(bot, "_cursor_cleanup"):
            del bot._cursor_cleanup
        # MagicMock always has attrs; force getattr path:
        bot = type("B", (), {"_sonata_cursor_cleanup_done": False})()
        super_close = AsyncMock()
        await close_with_cursor_cleanup(bot, sonata=sonata, super_close=super_close)
        cursor.cleanup.assert_awaited()
        super_close.assert_awaited()

    def test_index_sonata_client_close_delegates_to_helper(self):
        index_path = ROOT / "src" / "index.py"
        text = index_path.read_text()
        self.assertIn("close_with_cursor_cleanup", text)
        self.assertIn("async def close(self)", text)
        self.assertIn("super_close=super().close", text)
        self.assertNotIn('@bot.listen("on_close")', text)


if __name__ == "__main__":
    unittest.main()
