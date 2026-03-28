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

    def test_manual_group_resolution_and_group_rule_eval(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.upsert_group("chat", "mods", members=["7"])
        api.set_group_rule("chat", "mods", "chat.command.ban", "allow")

        groups = api.resolve_groups("chat", user_id=7)
        self.assertEqual(groups, ["chat:mods"])
        self.assertTrue(
            api.evaluate(
                "chat",
                "chat.command.ban",
                user_id=7,
            )
        )

    def test_role_derived_group_resolution(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.bind_group_role("chat", "admins", "role-admin")
        api.set_group_rule("chat", "admins", "chat.command.shutdown", "allow")

        groups = api.resolve_groups("chat", user_id=9, role_ids=["role-admin"])
        self.assertEqual(groups, ["chat:admins"])
        self.assertTrue(
            api.evaluate(
                "chat",
                "chat.command.shutdown",
                user_id=9,
                role_ids=["role-admin"],
            )
        )

    def test_mixed_group_membership_is_deterministic_with_deny_wins(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.upsert_group("chat", "mods", members=["7"])
        api.upsert_group("chat", "muted", members=["7"])
        api.set_group_rule("chat", "mods", "chat.command.kick", "allow")
        api.set_group_rule("chat", "muted", "chat.command.kick", "deny")

        self.assertFalse(api.evaluate("chat", "chat.command.kick", user_id=7))

    def test_group_lookup_is_namespace_safe(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.register_namespace("beacon", plugin=True)
        api.upsert_group("chat", "staff", members=["1"])
        api.upsert_group("beacon", "staff", members=["2"])

        self.assertEqual(api.resolve_groups("chat", user_id=1), ["chat:staff"])
        self.assertEqual(api.resolve_groups("beacon", user_id=2), ["beacon:staff"])
        self.assertEqual(api.resolve_groups("chat", user_id=2), [])

    def test_role_lookup_failures_fail_closed(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.bind_group_role("chat", "admins", "role-admin")
        api.set_group_rule("chat", "admins", "chat.command.shutdown", "allow")

        def broken_resolver(namespace, user_id):
            raise RuntimeError("role provider timeout")

        api.set_role_resolver(broken_resolver)
        self.assertFalse(api.evaluate("chat", "chat.command.shutdown", user_id=9))

    def test_group_runtime_resolution_sanity(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.upsert_group("chat", "g1", members=["7"])
        api.upsert_group("chat", "g2", members=["7"])
        api.upsert_group("chat", "g3", role_ids=["role3"])

        for _ in range(200):
            groups = api.resolve_groups("chat", user_id=7, role_ids=["role3"])
            self.assertEqual(groups, ["chat:g1", "chat:g2", "chat:g3"])

    def test_direct_user_allow_deny(self):
        policies = ChannelPolicies(FakeSonata())
        policies.set_user_flag(5, "can_speak", False)
        self.assertFalse(policies.can_speak(guild_id=1, channel_id=10, user_id=5))

        policies.set_user_flag(5, "can_speak", True)
        self.assertTrue(policies.can_speak(guild_id=1, channel_id=10, user_id=5))

    def test_group_targeted_user_effects_apply(self):
        policies = ChannelPolicies(FakeSonata())
        policies.upsert_user_group("mods", members=["7"])
        policies.deny_group_command("mods", "ban")

        self.assertFalse(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=10,
                user_id=7,
                command="ban",
            )
        )
        self.assertTrue(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=10,
                user_id=8,
                command="ban",
            )
        )

    def test_user_rule_interacts_with_group_and_deny_wins(self):
        policies = ChannelPolicies(FakeSonata())
        policies.upsert_user_group("mods", members=["7"])
        policies.deny_group_command("mods", "ban")
        policies.allow_user_command(7, "ban")

        self.assertFalse(
            policies.is_command_allowed(
                guild_id=1,
                channel_id=10,
                user_id=7,
                command="ban",
            )
        )

    def test_group_state_persists_across_channel_policies_reload(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)
        policies.upsert_user_group("mods", members=["7"], role_ids=["role-admin"])
        policies.deny_group_command("mods", "ban")

        sonata.policy_api = None
        reloaded = ChannelPolicies(sonata)
        self.assertEqual(
            reloaded.policy_api.get_group("chat", "mods"),
            {
                "id": "chat:mods",
                "members": ["7"],
                "roles": ["role-admin"],
            },
        )
        self.assertFalse(
            reloaded.is_command_allowed(
                guild_id=1,
                channel_id=10,
                user_id=7,
                command="ban",
            )
        )

    def test_precedence_user_channel_guild_and_namespace_isolation(self):
        api = PolicyAPI()
        api.register_namespace("chat", plugin=True)
        api.register_namespace("beacon", plugin=True)

        api.set_rule("chat", "guild", 1, "chat.command.ping", "allow")
        api.set_rule("chat", "channel", 2, "chat.command.ping", "allow")
        api.set_rule("chat", "user", 3, "chat.command.ping", "deny")

        self.assertFalse(
            api.evaluate(
                "chat", "chat.command.ping", guild_id=1, channel_id=2, user_id=3
            )
        )
        self.assertFalse(
            api.evaluate(
                "beacon",
                "chat.command.ping",
                guild_id=1,
                channel_id=2,
                user_id=3,
            )
        )

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


if __name__ == "__main__":
    unittest.main()
