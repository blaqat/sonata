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
policy_effects_mod = _load_module(
    "policy_effects", pathlib.Path("src/modules/policy_effects.py")
)
PolicyAPI = policy_api_mod.PolicyAPI
sync_chat_protected_effects = policy_effects_mod.sync_chat_protected_effects
beacon_chat_history_action = policy_effects_mod.beacon_chat_history_action


class FakeBranch:
    def __init__(self, store, path=()):
        self.store = store
        self.path = path
        self.home = "Beacon/Home"
        self.recast_names = store.setdefault("_recast_names", [])

    def branch(self, name):
        return type(self)(self.store, self.path + (name,))

    def recast(self, name=None, **_kwargs):
        self.recast_names.append(name)
        return self


class FakeSonata:
    def __init__(self):
        self.memory = {}
        self.sub_classes = {}
        self.beacon = FakeBranch({})
        self.sub_classes["beacon"] = self.beacon
        self.policy_api = PolicyAPI()
        self.policy_api.register_namespace(
            "chat",
            plugin=True,
            default_decisions={"chat.protected": False},
        )

    def has(self, name):
        return name in self.memory

    def hasPlugin(self, name):
        return name in self.sub_classes


class PolicyEffectsTests(unittest.TestCase):
    def test_has_stays_memory_only(self):
        sonata = FakeSonata()
        self.assertFalse(sonata.has("beacon"))
        self.assertTrue(sonata.hasPlugin("beacon"))

    def test_has_plugin_false_without_plugin(self):
        sonata = FakeSonata()
        del sonata.sub_classes["beacon"]
        del sonata.beacon
        self.assertFalse(sonata.hasPlugin("beacon"))

    def test_sync_recasts_channel_file_after_protect(self):
        sonata = FakeSonata()
        api = sonata.policy_api
        api.set_rule("chat", "channel", "44", "chat.protected", "allow")

        sync_chat_protected_effects(sonata, api)
        self.assertIn("i44", sonata.beacon.recast_names)

    def test_sync_sets_and_clears_beacon_encrypt_rule(self):
        sonata = FakeSonata()
        api = sonata.policy_api
        api.set_rule("chat", "channel", "44", "chat.protected", "allow")

        sync_chat_protected_effects(sonata, api)
        action = beacon_chat_history_action(sonata, "44")
        self.assertTrue(
            api.evaluate("beacon", action, guild_id="__global__", default=False)
        )

        api.remove_rule("chat", "channel", "44", "chat.protected")
        sync_chat_protected_effects(sonata, api, channel_ids=["44"])
        self.assertFalse(
            api.evaluate("beacon", action, guild_id="__global__", default=False)
        )


if __name__ == "__main__":
    unittest.main()
