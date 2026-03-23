import asyncio
import importlib.util
import pathlib
import sys
import unittest


repo_root = pathlib.Path(__file__).resolve().parents[1]
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))

from modules.term_console import TerminalConsole, _trim_base_path


def _load_term_commands_module():
    module_path = repo_root / "src" / "modules" / "plugins" / "term-commands.py"
    spec = importlib.util.spec_from_file_location("term_commands_plugin", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


class TermConsoleChatFormattingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.term_commands = _load_term_commands_module()

    def test_chat_line_uses_ansi_name_colors(self):
        line = self.term_commands.format_term_console_chat_line(
            42,
            "User",
            "Alice",
            "hello world",
        )
        self.assertIn("[chat:42]", line)
        self.assertIn("\033[1;38;2;", line)
        self.assertIn("Alice", line)

    def test_chat_line_includes_reply_context(self):
        line = self.term_commands.format_term_console_chat_line(
            42,
            "Bot",
            "sonata",
            "reply body",
            replying_to=("Bob", "previous message that should be previewed"),
        )
        self.assertIn("[bot]", line)
        self.assertIn("↪", line)
        self.assertIn("Bob", line)


if __name__ == "__main__":
    unittest.main()
