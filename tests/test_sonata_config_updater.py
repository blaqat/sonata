import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

repo_root = pathlib.Path(__file__).resolve().parents[1]
if str(repo_root / "src") not in sys.path:
    sys.path.insert(0, str(repo_root / "src"))

import sonata_config
from modules.AI_manager import AI_Manager
from sonata_config import (
    EDITABLE_FIELDS,
    ConfigUpdateError,
    RuntimeConfig,
    get_config_view,
    get_runtime_config,
    load_config,
    update_runtime_config,
)


class ConfigUpdaterTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config_path = pathlib.Path(self._tmp.name) / "sonata.config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "runtime": {"vc_recording": False},
                    "plugins": {
                        "chat": {
                            "bot_whitelist": ["BluBot", 1311742291521835048],
                            "auto": "c",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self._env_patcher = mock.patch.dict(
            "os.environ", {"SONATA_CONFIG": str(self.config_path)}
        )
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        runtime, _plugins = load_config(self.config_path)
        self.runtime = runtime

    def tearDown(self):
        self._tmp.cleanup()

    def test_assistant_ai_is_removed_from_editable_config(self):
        from modules.plugins import PLUGINS_DICT

        self.assertNotIn("openai_assistant", PLUGINS_DICT)
        self.assertNotIn("assistant", sonata_config._DEFAULT_AI_MODELS)
        self.assertNotIn("assistant", sonata_config._AI_MODEL_TO_TYPE)
        self.assertNotIn("runtime.ai_models.assistant", {f.path for f in EDITABLE_FIELDS})
        auto = next(f for f in EDITABLE_FIELDS if f.path == "plugins.chat.auto")
        self.assertNotIn("a", auto.options)
        self.assertEqual(auto.options, ("g", "o", "c", "m", "x"))

    def test_get_config_view_returns_only_allowlisted_fields(self):
        view = get_config_view()
        expected_paths = {f.path for f in EDITABLE_FIELDS}
        self.assertEqual(set(view["values"]), expected_paths)
        self.assertEqual({f["path"] for f in view["fields"]}, expected_paths)

    def test_get_runtime_config_is_the_safe_config_view(self):
        self.assertEqual(get_runtime_config(), get_config_view())

    def test_get_config_view_hides_non_editable_plugin_keys(self):
        blob = json.dumps(get_config_view())
        for hidden in ("tier1_user_ids", "tier2_user_ids", "default_repository_url"):
            self.assertNotIn(hidden, blob)

    def test_update_rejects_unknown_keys_without_writing(self):
        before = self.config_path.read_text(encoding="utf-8")
        with self.assertRaises(ConfigUpdateError) as ctx:
            update_runtime_config({"runtime.nope": True}, actor="test")
        self.assertIn("runtime.nope", ctx.exception.errors)
        self.assertEqual(before, self.config_path.read_text(encoding="utf-8"))

    def test_update_rejects_bad_values(self):
        with self.assertRaises(ConfigUpdateError) as ctx:
            update_runtime_config(
                {
                    "plugins.chat.auto": "zzz",
                    "plugins.chat.max_chats": "lots",
                    "plugins.chat.censor": "maybe",
                    "plugins.chat.bot_whitelist": [object()],
                },
                actor="test",
            )
        errors = ctx.exception.errors
        for path in (
            "plugins.chat.auto",
            "plugins.chat.max_chats",
            "plugins.chat.censor",
            "plugins.chat.bot_whitelist",
        ):
            self.assertIn(path, errors)
        self.assertFalse(self.config_path.exists() and "zzz" in self.config_path.read_text())

    def test_update_persists_and_hot_applies_runtime(self):
        result = update_runtime_config(
            {
                "runtime.vc_recording": True,
                "runtime.ai_models.openai": "gpt-test-hot",
            },
            actor="tester",
        )
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(saved["runtime"]["vc_recording"])
        self.assertEqual(saved["runtime"]["ai_models"]["openai"], "gpt-test-hot")
        self.assertTrue(self.runtime.vc_recording)
        self.assertIn("runtime.vc_recording", result["applied"])
        self.assertNotIn("runtime.vc_recording", result["restart_required"])
        self.assertEqual(result["values"]["runtime.vc_recording"], True)

    def test_update_normalizes_bot_whitelist_ids(self):
        update_runtime_config(
            {"plugins.chat.bot_whitelist": ["BluBot", "1311742291521835048", 42]},
            actor="tester",
        )
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        whitelist = saved["plugins"]["chat"]["bot_whitelist"]
        self.assertEqual(whitelist[0], "BluBot")
        self.assertIsInstance(whitelist[1], int)
        self.assertEqual(whitelist[1], 1311742291521835048)

    def test_update_flags_restart_required_keys(self):
        result = update_runtime_config(
            {
                "runtime.prompt_reset": True,
                "plugins.term_commands.inject_emojis": True,
            },
            actor="tester",
        )
        self.assertEqual(
            sorted(result["restart_required"]),
            [
                "plugins.term_commands.inject_emojis",
                "runtime.prompt_reset",
            ],
        )

    def test_update_logs_mutations_with_timestamp_and_actor(self):
        update_runtime_config({"plugins.chat.censor": True}, actor="web:abc123")
        view = get_config_view()
        entry = view["recent_mutations"][0]
        self.assertEqual(entry["actor"], "web:abc123")
        self.assertEqual(entry["changes"], {"plugins.chat.censor": True})
        self.assertIn("T", entry["timestamp"])

    def test_empty_update_is_rejected(self):
        with self.assertRaises(ConfigUpdateError):
            update_runtime_config({}, actor="test")

    def test_runtime_instance_shared_with_load_config_result(self):
        self.assertIsInstance(self.runtime, RuntimeConfig)
        update_runtime_config({"runtime.vc_speaking": False}, actor="tester")
        self.assertFalse(self.runtime.vc_speaking)

    def test_update_rejects_negative_max_chats(self):
        before = self.config_path.read_text(encoding="utf-8")
        with self.assertRaises(ConfigUpdateError) as ctx:
            update_runtime_config({"plugins.chat.max_chats": -1}, actor="test")
        self.assertIn("plugins.chat.max_chats", ctx.exception.errors)
        self.assertEqual(before, self.config_path.read_text(encoding="utf-8"))

    def test_update_rolls_back_document_when_save_fails(self):
        with mock.patch.object(
            sonata_config, "save_config", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                update_runtime_config({"plugins.chat.censor": True}, actor="test")
        view = get_config_view()
        self.assertFalse(view["values"]["plugins.chat.censor"])
        # A later successful save must not resurrect the rolled-back value.
        update_runtime_config({"runtime.vc_recording": True}, actor="test")
        saved = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertTrue(saved["runtime"]["vc_recording"])
        self.assertNotIn("censor", saved["plugins"]["chat"])

    def test_save_config_writes_to_explicitly_loaded_path(self):
        other_path = pathlib.Path(self._tmp.name) / "other.config.json"
        other_path.write_text(json.dumps({"runtime": {}}), encoding="utf-8")
        load_config(other_path)
        update_runtime_config({"runtime.vc_recording": True}, actor="test")
        saved = json.loads(other_path.read_text(encoding="utf-8"))
        self.assertTrue(saved["runtime"]["vc_recording"])
        original = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertFalse(original["runtime"]["vc_recording"])

    def test_nested_plugin_update_hot_applies_to_live_config(self):
        class FakeConfig:
            def __init__(self):
                self.values = {"search": {"num_results": 2}}

            def get(self, key, default=None):
                return self.values.get(key, default)

            def set(self, **updates):
                self.values.update(updates)

        manager = type("FakeManager", (), {"config": FakeConfig()})()
        with mock.patch.object(AI_Manager.M, "MANAGER", manager):
            sonata_config._live_apply_plugin(
                "plugins.self_commands.search.num_results", 7
            )
        self.assertEqual(manager.config.values["search"]["num_results"], 7)


if __name__ == "__main__":
    unittest.main()
