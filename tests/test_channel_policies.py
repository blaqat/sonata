import importlib.util
import pathlib
import unittest


def load_channel_policies_module():
    module_path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "src"
        / "modules"
        / "channel_policies.py"
    )
    spec = importlib.util.spec_from_file_location("channel_policies", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load channel_policies module spec")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


channel_policies = load_channel_policies_module()
normalize_channel_policy = channel_policies.normalize_channel_policy
normalize_allowed_commands = channel_policies.normalize_allowed_commands


class ChannelPolicyNormalizationTests(unittest.TestCase):
    def test_default_policy_keeps_wildcard(self):
        policy = normalize_channel_policy({"can_speak": True})
        self.assertEqual(policy["allowed_commands"], ["*"])

    def test_explicit_empty_allowed_commands_is_preserved(self):
        policy = normalize_channel_policy(
            {"can_speak": False, "allowed_commands": []}
        )
        self.assertEqual(policy["allowed_commands"], [])

    def test_explicit_none_allowed_commands_is_preserved_as_empty(self):
        policy = normalize_channel_policy(
            {"can_speak": False, "allowed_commands": None}
        )
        self.assertEqual(policy["allowed_commands"], [])

    def test_explicit_commands_are_normalized(self):
        policy = normalize_channel_policy(
            {"allowed_commands": ["$Ping", " ping ", "", None]}
        )
        self.assertEqual(policy["allowed_commands"], ["ping"])

    def test_normalize_allowed_commands_respects_fallback_flag(self):
        self.assertEqual(normalize_allowed_commands([], fallback_to_wildcard=True), ["*"])
        self.assertEqual(normalize_allowed_commands([], fallback_to_wildcard=False), [])


if __name__ == "__main__":
    unittest.main()
