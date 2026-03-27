import asyncio
import importlib.util
import pathlib
import re
import sys
import types
import unittest
from unittest import mock


def load_term_commands_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    if str(repo_root / "src") not in sys.path:
        sys.path.insert(0, str(repo_root / "src"))
    module_path = repo_root / "src" / "modules" / "plugins" / "term-commands.py"
    spec = importlib.util.spec_from_file_location("term_commands", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load term-commands module spec")

    discord_stub = types.ModuleType("discord")
    discord_stub.TextChannel = type("TextChannel", (), {})
    discord_stub.ChannelType = types.SimpleNamespace(voice="voice")
    discord_colour_stub = types.ModuleType("discord.colour")
    discord_colour_stub.Color = type("Color", (), {})
    annotated_stub = types.SimpleNamespace(IsInfinite=type("IsInfinite", (), {}))
    typing_extensions_stub = types.ModuleType("typing_extensions")
    typing_extensions_stub.cast = lambda _type, value: value
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *_, **__: None
    requests_stub = types.ModuleType("requests")

    class _DummyContext:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    prompt_toolkit_stub = types.ModuleType("prompt_toolkit")
    prompt_toolkit_stub.PromptSession = type("PromptSession", (), {})
    prompt_toolkit_formatted_stub = types.ModuleType("prompt_toolkit.formatted_text")
    prompt_toolkit_formatted_stub.ANSI = type("ANSI", (), {})
    prompt_toolkit_patch_stub = types.ModuleType("prompt_toolkit.patch_stdout")
    prompt_toolkit_patch_stub.patch_stdout = lambda *_, **__: _DummyContext()

    original_discord = sys.modules.get("discord")
    original_discord_colour = sys.modules.get("discord.colour")
    original_annotated = sys.modules.get("annotated_types")
    original_typing_extensions = sys.modules.get("typing_extensions")
    original_dotenv = sys.modules.get("dotenv")
    original_requests = sys.modules.get("requests")
    original_prompt_toolkit = sys.modules.get("prompt_toolkit")
    original_prompt_toolkit_formatted = sys.modules.get("prompt_toolkit.formatted_text")
    original_prompt_toolkit_patch = sys.modules.get("prompt_toolkit.patch_stdout")
    sys.modules["discord"] = discord_stub
    sys.modules["discord.colour"] = discord_colour_stub
    sys.modules["annotated_types"] = annotated_stub
    sys.modules["typing_extensions"] = typing_extensions_stub
    sys.modules["dotenv"] = dotenv_stub
    sys.modules["requests"] = requests_stub
    sys.modules["prompt_toolkit"] = prompt_toolkit_stub
    sys.modules["prompt_toolkit.formatted_text"] = prompt_toolkit_formatted_stub
    sys.modules["prompt_toolkit.patch_stdout"] = prompt_toolkit_patch_stub
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if original_discord is None:
            sys.modules.pop("discord", None)
        else:
            sys.modules["discord"] = original_discord
        if original_discord_colour is None:
            sys.modules.pop("discord.colour", None)
        else:
            sys.modules["discord.colour"] = original_discord_colour
        if original_annotated is None:
            sys.modules.pop("annotated_types", None)
        else:
            sys.modules["annotated_types"] = original_annotated
        if original_typing_extensions is None:
            sys.modules.pop("typing_extensions", None)
        else:
            sys.modules["typing_extensions"] = original_typing_extensions
        if original_dotenv is None:
            sys.modules.pop("dotenv", None)
        else:
            sys.modules["dotenv"] = original_dotenv
        if original_requests is None:
            sys.modules.pop("requests", None)
        else:
            sys.modules["requests"] = original_requests
        if original_prompt_toolkit is None:
            sys.modules.pop("prompt_toolkit", None)
        else:
            sys.modules["prompt_toolkit"] = original_prompt_toolkit
        if original_prompt_toolkit_formatted is None:
            sys.modules.pop("prompt_toolkit.formatted_text", None)
        else:
            sys.modules["prompt_toolkit.formatted_text"] = original_prompt_toolkit_formatted
        if original_prompt_toolkit_patch is None:
            sys.modules.pop("prompt_toolkit.patch_stdout", None)
        else:
            sys.modules["prompt_toolkit.patch_stdout"] = original_prompt_toolkit_patch
    return module


term_commands = load_term_commands_module()
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class TermCommandRegistryTests(unittest.TestCase):
    def tearDown(self):
        commands = term_commands.MANAGER.get("termcmd", "value")
        for key in ["dummy", "doc", "nodesc"]:
            if key in commands:
                del commands[key]

    def test_term_command_registration_sets_description(self):
        async def dummy():
            """Dummy description"""
            return None

        term_commands.term_command(dummy, name="dummy", description="Custom desc")
        commands = term_commands.MANAGER.get("termcmd", "value")
        self.assertEqual(commands["dummy"]["description"], "Custom desc")

    def test_term_command_registration_falls_back_to_docstring(self):
        async def doc():
            """Doc description"""
            return None

        term_commands.term_command(doc, name="doc")
        commands = term_commands.MANAGER.get("termcmd", "value")
        self.assertEqual(commands["doc"]["description"], "Doc description")

    def test_build_help_lines_uses_fallback_when_missing(self):
        async def nodesc():
            return None

        commands = {
            "b": {"func": nodesc, "description": None},
            "a": {"func": nodesc, "description": None},
        }
        lines = term_commands._build_help_lines(commands)
        self.assertEqual(ANSI_RE.sub("", lines[0]).strip(), "a: No description available.")
        self.assertEqual(ANSI_RE.sub("", lines[1]).strip(), "b: No description available.")


class TermConsolePrintTests(unittest.IsolatedAsyncioTestCase):
    async def test_console_cprint_emits_ansi_styled_output(self):
        styled_text = "\x1b[31mhello\x1b[0m"

        class _Loop:
            def create_task(self, coro):
                return asyncio.create_task(coro)

        with (
            mock.patch.object(term_commands, "base_cprint") as base_cprint,
            mock.patch.object(term_commands, "cstrs", return_value=styled_text) as cstrs,
            mock.patch.object(term_commands.asyncio, "get_running_loop", return_value=_Loop()),
        ):
            await term_commands.TERM_CONSOLE.clear_all_sessions()
            term_commands._console_cprint("hello", "red")
            await asyncio.sleep(0)

        base_cprint.assert_called_once_with("hello", "red")
        cstrs.assert_called_once_with("hello", "red")
        history = term_commands.TERM_CONSOLE.snapshot_for("alpha")["history"]
        self.assertEqual(history[-1]["text"], styled_text)
        self.assertEqual(history[-1]["stream"], "stdout")


if __name__ == "__main__":
    unittest.main()
