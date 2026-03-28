import importlib.util
import pathlib
import sys
import unittest


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


policy_api_mod = _load_module("policy_api", pathlib.Path("src/modules/policy_api.py"))
channel_policies_mod = _load_module(
    "channel_policies", pathlib.Path("src/modules/channel_policies.py")
)

ALLOWLIST = channel_policies_mod.ALLOWLIST
ChannelPolicies = channel_policies_mod.ChannelPolicies
PolicyAPI = policy_api_mod.PolicyAPI


class FakeConfig:
    def __init__(self):
        self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, **kwargs):
        self.data.update(kwargs)


class FakeBranch:
    def __init__(self, store, path=()):
        self.store = store
        self.path = path

    def branch(self, name):
        return type(self)(self.store, self.path + (name,))

    def illuminate(self, name, data):
        self.store[self.path + (name,)] = data
        return self

    def discover(self, name):
        return self.store.get(self.path + (name,))


class FakeSonata:
    def __init__(self):
        self.config = FakeConfig()
        self._beacon_store = {}
        self.beacon = FakeBranch(self._beacon_store)


class PolicyApiTests(unittest.TestCase):
    def test_duplicate_namespace_registration_is_rejected(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        with self.assertRaises(ValueError):
            api.register_namespace("chat", plugin=True)

    def test_precedence_and_deny_wins(self):
        api = PolicyAPI()
        api.register_namespace(
            "chat", plugin=True, default_decisions={"chat.can_speak": True}
        )
        api.set_rule("chat", "guild", 1, "chat.can_speak", "allow")
        api.set_rule("chat", "channel", 2, "chat.can_speak", "allow")
        api.set_rule("chat", "user", 3, "chat.can_speak", "allow")

        self.assertTrue(
            api.evaluate("chat", "chat.can_speak", guild_id=1, channel_id=2, user_id=3)
        )

        api.set_rule("chat", "guild", 1, "chat.can_speak", "deny")
        self.assertFalse(
            api.evaluate("chat", "chat.can_speak", guild_id=1, channel_id=2, user_id=3)
        )

    def test_namespace_isolation(self):
        api = PolicyAPI()
        api.register_namespace(
            "chat", plugin=True, default_decisions={"chat.command.*": True}
        )
        api.register_namespace(
            "beacon", plugin=True, default_decisions={"beacon.encrypt": False}
        )

        api.set_rule("chat", "channel", 22, "chat.command.ping", "deny")

        self.assertFalse(api.evaluate("chat", "chat.command.ping", channel_id=22))
        self.assertFalse(api.evaluate("beacon", "beacon.encrypt", channel_id=22))

    def test_plugin_unload_makes_namespace_rules_inert(self):
        api = PolicyAPI()
        api.register_namespace(
            "chat", plugin=True, default_decisions={"chat.command.*": True}
        )
        api.set_rule("chat", "channel", 11, "chat.command.help", "deny")

        self.assertFalse(api.evaluate("chat", "chat.command.help", channel_id=11))
        api.unload_namespace("chat")
        self.assertTrue(api.evaluate("chat", "chat.command.help", channel_id=11))

    def test_core_namespace_guild_rules_work_without_plugins(self):
        api = PolicyAPI()
        api.set_rule("core", "guild", 1, "core.feature.chat", "allow")
        self.assertTrue(api.evaluate("core", "core.feature.chat", guild_id=1))
        self.assertFalse(api.evaluate("core", "core.feature.chat", guild_id=2))

    def test_channel_policy_behavior_migrates_via_policy_api(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)

        self.assertTrue(policies.can_speak(guild_id=1, channel_id=100, user_id=7))
        self.assertFalse(
            policies.should_respond_all(guild_id=1, channel_id=100, user_id=7)
        )
        self.assertTrue(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=100,
                user_id=7,
                command="help",
            )
        )

        policies.deny_command(100, "help")
        self.assertFalse(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=100,
                user_id=7,
                command="help",
            )
        )
        self.assertTrue(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=100,
                user_id=7,
                command="ping",
            )
        )

        policies.blacklist_add(300)
        self.assertFalse(policies.can_speak(guild_id=1, channel_id=300, user_id=7))

        policies.set_channel_flag(300, "respond_all", True)
        self.assertTrue(
            policies.should_respond_all(guild_id=1, channel_id=300, user_id=7)
        )

        policies.set_channel_policy(
            200,
            command_policy_mode=ALLOWLIST,
            commands=["help"],
        )
        self.assertTrue(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=200,
                user_id=7,
                command="help",
            )
        )
        self.assertFalse(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=200,
                user_id=7,
                command="ping",
            )
        )

    def test_channel_policies_reactivate_chat_namespace_on_reuse(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)
        policies.deny_command(100, "help")

        policies.policy_api.unload_namespace("chat")

        reloaded = ChannelPolicies(sonata)
        self.assertFalse(
            reloaded.is_command_allowed(
                guild_id=1,
                channel_id=100,
                user_id=7,
                command="help",
            )
        )

    def test_guild_baseline_policy_applies_without_higher_scopes(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)

        policies.set_guild_flag(1, "can_speak", False)
        self.assertFalse(policies.can_speak(guild_id=1, channel_id=900, user_id=7))

        policies.set_guild_flag(2, "respond_all", True)
        self.assertTrue(
            policies.should_respond_all(guild_id=2, channel_id=901, user_id=8)
        )

    def test_guild_deny_wins_over_higher_scope_allow(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)

        policies.set_guild_flag(1, "can_speak", False)
        policies.set_channel_flag(100, "can_speak", True)
        self.assertFalse(policies.can_speak(guild_id=1, channel_id=100, user_id=7))

    def test_guild_isolation_has_no_cross_guild_bleed(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)

        policies.set_guild_flag(1, "respond_all", True)
        self.assertTrue(
            policies.should_respond_all(guild_id=1, channel_id=10, user_id=1)
        )
        self.assertFalse(
            policies.should_respond_all(guild_id=2, channel_id=10, user_id=1)
        )


if __name__ == "__main__":
    unittest.main()
