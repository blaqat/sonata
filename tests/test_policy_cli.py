import asyncio
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import MagicMock


def _load_module(module_name, relative_path):
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    module_path = repo_root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load {module_name} module spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# policy_cli imports policy_admin only in docstring conceptually; load deps first
_load_module("policy_api", pathlib.Path("src/modules/policy_api.py"))
policy_cli_mod = _load_module("policy_cli", pathlib.Path("src/modules/policy_cli.py"))
dispatch_policy_command = policy_cli_mod.dispatch_policy_command


class PolicyCliDispatchTests(unittest.TestCase):
    def test_namespaces_and_set_use_resolvers(self):
        admin = MagicMock()
        admin.list_namespaces.return_value = ["chat", "core"]
        admin.set_rule.return_value = "ok"

        async def resolve_target(scope, target):
            self.assertEqual(scope, "channel")
            self.assertEqual(target, "here")
            return "99"

        result = asyncio.run(
            dispatch_policy_command(
                admin,
                "namespaces",
                [],
                "usage",
                resolve_target=resolve_target,
                format_namespace=lambda n: f"`{n}`",
            )
        )
        self.assertEqual(result, "Namespaces: `chat`, `core`")

        result = asyncio.run(
            dispatch_policy_command(
                admin,
                "set",
                ["chat", "channel", "here", "chat.can_speak", "deny"],
                "usage",
                resolve_target=resolve_target,
            )
        )
        self.assertEqual(result, "ok")
        admin.set_rule.assert_called_once_with(
            "chat", "channel", "99", "chat.can_speak", "deny"
        )

    def test_unknown_action_returns_none(self):
        admin = MagicMock()

        async def resolve_target(scope, target):
            return target

        result = asyncio.run(
            dispatch_policy_command(
                admin,
                "nope",
                [],
                "usage",
                resolve_target=resolve_target,
            )
        )
        self.assertIsNone(result)

    def test_groups_member_validates_user(self):
        admin = MagicMock()
        admin.add_group_member.return_value = "added"
        seen = {}

        async def resolve_target(scope, target):
            return target

        async def validate_user(user_id):
            seen["user"] = user_id
            return user_id

        result = asyncio.run(
            dispatch_policy_command(
                admin,
                "groups",
                ["member", "add", "chat", "mods", "<@7>"],
                "usage",
                resolve_target=resolve_target,
                resolve_user_id=lambda raw: "7",
                validate_user=validate_user,
            )
        )
        self.assertEqual(result, "added")
        self.assertEqual(seen["user"], "7")
        admin.add_group_member.assert_called_once_with("chat", "mods", "7")

    def test_actions_lists_namespace_actions(self):
        admin = MagicMock()
        admin.list_actions.return_value = "Actions in `chat`:\n  chat.protected (default deny)"

        async def resolve_target(scope, target):
            return target

        result = asyncio.run(
            dispatch_policy_command(
                admin,
                "actions",
                ["chat"],
                "usage",
                resolve_target=resolve_target,
            )
        )
        self.assertIn("chat.protected", result)
        admin.list_actions.assert_called_once_with("chat")

    def test_actions_accepts_prefix(self):
        admin = MagicMock()
        admin.list_actions.return_value = "Actions matching `chat.command`:"

        async def resolve_target(scope, target):
            return target

        result = asyncio.run(
            dispatch_policy_command(
                admin,
                "actions",
                ["chat.command"],
                "usage",
                resolve_target=resolve_target,
            )
        )
        self.assertIn("chat.command", result)
        admin.list_actions.assert_called_once_with("chat.command")


if __name__ == "__main__":
    unittest.main()
