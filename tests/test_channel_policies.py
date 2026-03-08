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
ALLOWLIST = channel_policies.ALLOWLIST
DENYLIST = channel_policies.DENYLIST
ChannelPolicy = channel_policies.ChannelPolicy
ChannelPolicies = channel_policies.ChannelPolicies
has_manage_guild_permission = channel_policies.has_manage_guild_permission
normalize_commands = channel_policies.normalize_commands
parse_channel_reference = channel_policies.parse_channel_reference
resolve_channel_in_guild = channel_policies.resolve_channel_in_guild
should_respond_to_message = channel_policies.should_respond_to_message
should_track_message = channel_policies.should_track_message


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


class FakeChannel:
    def __init__(self, channel_id):
        self.id = channel_id


class FakeGuild:
    def __init__(self, channels):
        self.channels = channels

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)


class ChannelPolicyTests(unittest.TestCase):
    def test_default_policy_is_open_denylist(self):
        policy = ChannelPolicy.default()
        self.assertTrue(policy.can_speak)
        self.assertFalse(policy.respond_all)
        self.assertEqual(policy.command_policy_mode, DENYLIST)
        self.assertEqual(policy.commands, [])
        self.assertTrue(policy.allows_command("help"))

    def test_blacklisted_policy_disables_sonata(self):
        policy = ChannelPolicy.blacklisted()
        self.assertFalse(policy.can_speak)
        self.assertEqual(policy.command_policy_mode, ALLOWLIST)
        self.assertEqual(policy.commands, [])
        self.assertFalse(should_track_message(policy))

    def test_denylist_policy_denies_only_listed_commands(self):
        policy = ChannelPolicy.default().deny_command("$Help")
        self.assertEqual(policy.commands, ["help"])
        self.assertFalse(policy.allows_command("help"))
        self.assertTrue(policy.allows_command("ping"))

    def test_allowlist_policy_allows_only_listed_commands(self):
        policy = ChannelPolicy(
            can_speak=True,
            command_policy_mode=ALLOWLIST,
            commands=[],
        ).allow_command("help")
        self.assertEqual(policy.commands, ["help"])
        self.assertTrue(policy.allows_command("help"))
        self.assertFalse(policy.allows_command("ping"))

    def test_allow_on_denylist_removes_denied_command(self):
        policy = ChannelPolicy.default().deny_command("help").allow_command("help")
        self.assertEqual(policy.commands, [])
        self.assertTrue(policy.allows_command("help"))

    def test_deny_on_allowlist_removes_allowed_command(self):
        policy = ChannelPolicy(
            can_speak=True,
            command_policy_mode=ALLOWLIST,
            commands=["help", "ping"],
        ).deny_command("ping")
        self.assertEqual(policy.commands, ["help"])
        self.assertFalse(policy.allows_command("ping"))

    def test_command_normalization_strips_prefix_and_duplicates(self):
        self.assertEqual(
            normalize_commands(["$Ping", " ping ", "", None, "PING"]),
            ["ping"],
        )

    def test_channel_manager_blacklist_round_trip_restores_default(self):
        sonata = FakeSonata()
        policies = ChannelPolicies(sonata)

        blacklisted = policies.blacklist_add(123)
        self.assertFalse(blacklisted.can_speak)
        self.assertEqual(blacklisted.command_policy_mode, ALLOWLIST)
        self.assertEqual(blacklisted.commands, [])

        restored = policies.blacklist_remove(123)
        self.assertTrue(restored.can_speak)
        self.assertEqual(restored.command_policy_mode, DENYLIST)
        self.assertEqual(restored.commands, [])
        self.assertEqual(
            sonata._beacon_store[("policies", "channels")]["123"]["command_policy_mode"],
            DENYLIST,
        )

    def test_missing_permissions_are_denied(self):
        class Permissions:
            manage_guild = False

        class Author:
            guild_permissions = Permissions()

        class Ctx:
            author = Author()

        self.assertFalse(has_manage_guild_permission(Ctx()))
        self.assertFalse(has_manage_guild_permission(object()))

    def test_manage_guild_permission_is_allowed(self):
        class Permissions:
            manage_guild = True

        class Author:
            guild_permissions = Permissions()

        class Ctx:
            author = Author()

        self.assertTrue(has_manage_guild_permission(Ctx()))

    def test_non_directed_messages_still_track_but_do_not_respond(self):
        policy = ChannelPolicy.default()
        self.assertTrue(should_track_message(policy))
        self.assertFalse(
            should_respond_to_message(
                policy,
                is_command=False,
                is_reply_to_sonata=False,
                called_sonata=False,
            )
        )

    def test_channel_reference_accepts_exact_id_or_mention(self):
        self.assertEqual(parse_channel_reference("12345"), 12345)
        self.assertEqual(parse_channel_reference("<#12345>"), 12345)

    def test_channel_reference_rejects_channel_names(self):
        self.assertIsNone(parse_channel_reference("general-2"))
        self.assertIsNone(parse_channel_reference("#general"))

    def test_resolve_channel_in_guild_rejects_names_and_resolves_mentions(self):
        guild = FakeGuild({12345: FakeChannel(12345)})
        channel, error = resolve_channel_in_guild(guild, "<#12345>")
        self.assertEqual(channel.id, 12345)
        self.assertIsNone(error)

        channel, error = resolve_channel_in_guild(guild, "general-2")
        self.assertIsNone(channel)
        self.assertEqual(
            error,
            "Channel must be a channel id or Discord channel mention.",
        )


if __name__ == "__main__":
    unittest.main()
