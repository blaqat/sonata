import ast
import importlib.util
import pathlib
import types
import unittest
from typing import Optional, Union


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _load_author_in_whitelist():
    module_path = SRC_ROOT / "modules" / "bot_whitelist.py"
    spec = importlib.util.spec_from_file_location("bot_whitelist_helper_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.author_in_whitelist


def _load_process_commands(author_in_whitelist):
    source = (SRC_ROOT / "__init__.py").read_text()
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "process_commands"
    )
    namespace = {
        "author_in_whitelist": author_in_whitelist,
        "Optional": Optional,
        "Union": Union,
        "Message": object,
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), "src/__init__.py", "exec"),
        namespace,
    )
    return namespace["process_commands"]


def _author(**overrides):
    author = types.SimpleNamespace(
        bot=True,
        id=1311742291521835048,
        name="blubot_user",
        display_name="BluBot",
    )
    author.__dict__.update(overrides)
    return author


_MATCH = _load_author_in_whitelist()
_PROCESS_COMMANDS = _load_process_commands(_MATCH)


class AuthorInWhitelistTests(unittest.TestCase):
    def test_matches_numeric_id(self):
        author = _author(name="other", display_name="Other")
        self.assertTrue(_MATCH(author, [author.id, "SomeoneElse"]))

    def test_matches_username_case_insensitively(self):
        author = _author(name="BluBotUser", display_name="Nickname")
        self.assertTrue(_MATCH(author, ["blubotuser"]))

    def test_matches_display_name_case_insensitively(self):
        author = _author(name="blubot_user", display_name="BluBot")
        self.assertTrue(_MATCH(author, ["blubot"]))

    def test_rejects_unrelated_name_and_id(self):
        author = _author()
        self.assertFalse(_MATCH(author, ["NotBlu", 1]))

    def test_empty_or_missing_whitelist_is_not_a_match(self):
        author = _author()
        self.assertFalse(_MATCH(author, []))
        self.assertFalse(_MATCH(author, None))


class ProcessCommandsWhitelistTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, author, whitelist):
        processed = []

        class _PatchedBot:
            async def get_context(self, message):
                return message

            async def invoke(self, ctx):
                processed.append(ctx.content)

        message = types.SimpleNamespace(author=author, content="$help")
        await _PROCESS_COMMANDS(_PatchedBot(), message, bot_whitelist=whitelist)
        return processed

    async def test_id_match_processes_command(self):
        author = _author(name="other", display_name="Other")
        processed = await self._run(author, [author.id])
        self.assertEqual(processed, ["$help"])

    async def test_username_match_processes_command(self):
        author = _author(name="BluBotUser", display_name="Nickname")
        processed = await self._run(author, ["blubotuser"])
        self.assertEqual(processed, ["$help"])

    async def test_display_name_match_processes_command(self):
        author = _author()
        processed = await self._run(author, ["BluBot"])
        self.assertEqual(processed, ["$help"])

    async def test_non_match_skips_command(self):
        processed = await self._run(_author(), ["NotBlu", 1])
        self.assertEqual(processed, [])

    async def test_empty_whitelist_skips_bot_command(self):
        processed = await self._run(_author(), [])
        self.assertEqual(processed, [])


if __name__ == "__main__":
    unittest.main()
