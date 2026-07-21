"""Production close path must invoke Cursor cleanup (py-cord has no on_close)."""

from __future__ import annotations
from contextlib import contextmanager

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
        rt = mod.CursorRuntime(
            expiry_task=expiry,
            reconcile_task=reconcile,
            trackers={"a1": tracker},
            client=client,
            cdn=cdn,
        )
        mod.set_runtime(rt)

        bot = MagicMock()
        bot._cursor_runtime = rt
        super_close = AsyncMock()

        await close_with_cursor_cleanup(bot, sonata=None, super_close=super_close)
        await close_with_cursor_cleanup(bot, sonata=None, super_close=super_close)

        self.assertTrue(rt.closed)
        self.assertTrue(expiry.cancelled() or expiry.done())
        self.assertTrue(reconcile.cancelled() or reconcile.done())
        self.assertTrue(tracker.cancelled() or tracker.done())
        client.aclose.assert_awaited_once()
        cdn.aclose.assert_awaited_once()
        self.assertEqual(super_close.await_count, 2)

    async def test_close_skips_when_no_cursor_runtime(self):
        cursor = MagicMock()
        cursor.cleanup = AsyncMock()
        sonata = MagicMock()
        sonata.cursor = cursor
        sonata.get = MagicMock(return_value=None)
        bot = type("B", (), {})()
        super_close = AsyncMock()
        await close_with_cursor_cleanup(bot, sonata=sonata, super_close=super_close)
        cursor.cleanup.assert_not_awaited()
        super_close.assert_awaited()

    def test_index_sonata_client_close_delegates_to_helper(self):
        index_path = ROOT / "src" / "index.py"
        shutdown_path = ROOT / "src" / "modules" / "cursor_shutdown.py"
        index_text = index_path.read_text()
        shutdown_text = shutdown_path.read_text()
        self.assertIn("close_with_cursor_cleanup", index_text)
        self.assertIn("async def close(self)", index_text)
        self.assertIn("super_close=super().close", index_text)
        self.assertNotIn("_sonata_cursor_cleanup_done", index_text)
        self.assertIn("_cursor_runtime", shutdown_text)
        self.assertNotIn('@bot.listen("on_close")', index_text)


if __name__ == "__main__":
    unittest.main()
