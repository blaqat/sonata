import asyncio
import pathlib
import sys
import unittest


repo_root = pathlib.Path(__file__).resolve().parents[1]
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))

from modules.term_console import TerminalConsole, _trim_base_path


class TerminalConsoleTests(unittest.IsolatedAsyncioTestCase):
    async def test_controller_takeover_requires_force(self):
        console = TerminalConsole()
        ok, _ = await console.set_controller("alpha", force=False)
        self.assertTrue(ok)
        ok, message = await console.set_controller("bravo", force=False)
        self.assertFalse(ok)
        self.assertIn("control", message.lower())
        ok, message = await console.set_controller("bravo", force=True)
        self.assertTrue(ok)
        self.assertEqual(console.controller_id, "bravo")

    async def test_prompt_response_round_trip(self):
        console = TerminalConsole()
        await console.set_controller("alpha")

        async def answer():
            await asyncio.sleep(0)
            pending = console.pending_prompts["alpha"]
            ok, _ = await console.submit_prompt_response(
                "alpha",
                pending.prompt_id,
                "value",
            )
            self.assertTrue(ok)

        waiter = asyncio.create_task(console.request_prompt("alpha", "Enter value"))
        responder = asyncio.create_task(answer())
        result = await waiter
        await responder
        self.assertEqual(result, "value")

    async def test_command_rejected_without_control(self):
        console = TerminalConsole()

        async def runner():
            return None

        ok, message = await console.run_command("alpha", "help", runner)
        self.assertFalse(ok)
        self.assertIn("controller", message.lower())

    async def test_snapshot_includes_history(self):
        console = TerminalConsole()
        await console.emit_output("hello")
        snapshot = console.snapshot_for("alpha")
        self.assertEqual(snapshot["history"][0]["text"], "hello")


class TermConsoleRouteTests(unittest.TestCase):
    def test_trim_base_path(self):
        self.assertEqual(_trim_base_path("/", "/"), "")
        self.assertEqual(_trim_base_path("/api/session", "/"), "/api/session")
        self.assertEqual(_trim_base_path("/term-console", "/term-console"), "")
        self.assertEqual(
            _trim_base_path("/term-console/api/session", "/term-console"),
            "/api/session",
        )
        self.assertIsNone(_trim_base_path("/other", "/term-console"))


if __name__ == "__main__":
    unittest.main()
