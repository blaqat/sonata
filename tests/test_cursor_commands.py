import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import MagicMock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.config import DEFAULT_PLUGIN_CONFIG, load_cursor_config
from cursor_cloud.access import AccessController, MemoryAccessStore
from cursor_cloud.models import AccessTier


def load_cursor_plugin():
    """Load plugin module without permanently hijacking AI_Manager.M.MANAGER."""
    from modules.AI_manager import AI_Manager

    path = ROOT / "src" / "modules" / "plugins" / "cursor-commands.py"
    spec = importlib.util.spec_from_file_location("cursor_commands_plugin", path)
    module = importlib.util.module_from_spec(spec)
    previous_manager = AI_Manager.M.MANAGER
    try:
        spec.loader.exec_module(module)
    finally:
        # cursor-commands uses AI_Manager.init(lazy=True), which rebinds the
        # shared facade; restore so later suite modules keep their managers.
        AI_Manager.M.MANAGER = previous_manager
    return module


class TestConfigDefaults(unittest.TestCase):
    def test_defaults_and_secret_not_from_json(self):
        cfg = load_cursor_config(
            {"enabled": True, "default_repository_url": "https://github.com/o/r", "CURSOR_API_KEY": "leak"},
            env={"GOD": "123456789012345678", "CURSOR_API_KEY": "real"},
        )
        self.assertEqual(cfg.api_key, "real")
        self.assertEqual(cfg.access.default_grant_minutes, 10)
        self.assertEqual(cfg.access.approval_timeout_hours, 12)
        self.assertEqual(cfg.session_idle_prompt_minutes, 10)
        self.assertIn("access", DEFAULT_PLUGIN_CONFIG)


class TestCommandRegistration(unittest.TestCase):
    def test_register_commands_idempotent(self):
        mod = load_cursor_plugin()
        bot = MagicMock()
        bot.pending_application_commands = []
        bot.application_commands = []

        def add(cmd):
            bot.pending_application_commands.append(cmd)

        bot.add_application_command.side_effect = add
        mod._register_commands(bot)
        mod._register_commands(bot)
        self.assertEqual(bot.add_application_command.call_count, 1)
        self.assertEqual(bot.pending_application_commands[0].name, "cursor")

    def test_group_has_required_subcommands(self):
        mod = load_cursor_plugin()
        names = {c.name for c in mod.cursor_group.walk_commands()}
        for required in {"run", "stop", "sessions", "session", "model", "status"}:
            self.assertIn(required, names)

    def test_option_raw_types_are_classes_under_future_annotations(self):
        """Regression: Option-as-annotation + future annotations made _raw_type a
        string, crashing py-cord invoke with issubclass() TypeError."""
        import discord
        from discord import SlashCommandOptionType

        mod = load_cursor_plugin()
        by_name = {c.name: c for c in mod.cursor_group.subcommands}
        model = by_name["model"]
        self.assertIs(model.options[0]._raw_type, str)
        self.assertEqual(model.options[0].input_type, SlashCommandOptionType.string)

        run = by_name["run"]
        image_opts = [o for o in run.options if o.name.startswith("image")]
        self.assertEqual(len(image_opts), 5)
        for op in image_opts:
            self.assertIs(op._raw_type, discord.Attachment)
            self.assertEqual(op.input_type, SlashCommandOptionType.attachment)

        stop = by_name["stop"]
        self.assertIs(stop.options[0]._raw_type, discord.User)
        self.assertEqual(stop.options[0].input_type, SlashCommandOptionType.user)


class TestPolicyCommandNames(unittest.IsolatedAsyncioTestCase):
    async def test_tier_gates_before_policy_semantics(self):
        god = "100000000000000001"
        t2 = "100000000000000002"
        other = "100000000000000003"
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier2_user_ids": [t2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": god},
        )
        ctrl = AccessController(cfg, MemoryAccessStore())
        self.assertEqual(await ctrl.resolve_tier(god), AccessTier.GOD)
        self.assertEqual(await ctrl.resolve_tier(t2), AccessTier.APPROVAL)
        self.assertTrue(await ctrl.can_use_command(t2, "status"))
        self.assertTrue(await ctrl.can_use_command(t2, "run"))
        self.assertFalse(await ctrl.can_use_command(t2, "access"))
        self.assertFalse(await ctrl.can_use_command(other, "run"))


if __name__ == "__main__":
    unittest.main()
