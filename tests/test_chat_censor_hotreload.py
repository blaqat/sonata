import importlib.util
import pathlib
import re
import sys
import types
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _load_bot_whitelist():
    module_path = SRC_ROOT / "modules" / "bot_whitelist.py"
    spec = importlib.util.spec_from_file_location("modules.bot_whitelist", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_chat_module():
    module_path = SRC_ROOT / "modules" / "plugins" / "chat.py"
    spec = importlib.util.spec_from_file_location("chat_censor_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load chat module spec")

    class _Manager:
        @staticmethod
        def _decorator(*args, **kwargs):
            if len(args) == 1 and callable(args[0]) and not kwargs:
                return args[0]
            return lambda function: function

        builder = _decorator
        effect = _decorator
        effect_post = _decorator
        mem = _decorator
        prompt = _decorator
        with_context = _decorator

    manager = _Manager()
    context = types.SimpleNamespace(plugin_config={})
    prompt_manager = types.SimpleNamespace()

    class _Facade:
        MANAGER = None

    class _AIManager:
        M = _Facade()

        @staticmethod
        def init(*_args, lazy=False, config=None, **_kwargs):
            context.plugin_config = dict(config or {})
            return context, manager, prompt_manager

    ai_manager_stub = types.ModuleType("modules.AI_manager")
    ai_manager_stub.AI_Manager = _AIManager
    ai_manager_stub.Context = object

    channel_policies_stub = types.ModuleType("modules.channel_policies")
    channel_policies_stub.LEGACY_CHANNEL_BLACKLIST = set()
    channel_policies_stub.ChannelPolicies = object
    channel_policies_stub.get_channel_policy = lambda *_args, **_kwargs: {}
    channel_policies_stub.get_command_name = lambda *_args, **_kwargs: None

    utils_stub = types.ModuleType("modules.utils")
    utils_stub.censor_message = _censor_message
    utils_stub.async_print = lambda *_args, **_kwargs: None
    utils_stub.async_cprint = lambda *_args, **_kwargs: None
    utils_stub.cstr = lambda **kwargs: kwargs["str"]
    utils_stub.classify_ai_error = lambda *_args, **_kwargs: ("internal", "")
    utils_stub.TRANSIENT_AI_ERRORS = tuple()
    utils_stub.get_full_name = lambda *_args, **_kwargs: ""
    utils_stub.setter = lambda *_args, **_kwargs: None
    utils_stub.settings = types.SimpleNamespace(TENOR_G="", KLIPY="")
    utils_stub.has_inside = lambda *_args, **_kwargs: False
    utils_stub.get_reference_message = lambda *_args, **_kwargs: None
    utils_stub.get_reference_chain = lambda *_args, **_kwargs: []
    utils_stub.gif_provider_get_dl_url = lambda url, *_args, **_kwargs: url
    utils_stub.get_trace = lambda: ""

    discord_stub = types.ModuleType("discord")
    discord_stub.Message = object
    discord_stub.utils = types.SimpleNamespace(utcnow=lambda: None)
    discord_ext_stub = types.ModuleType("discord.ext")
    commands_stub = types.ModuleType("discord.ext.commands")
    commands_stub.Bot = object
    discord_ext_stub.commands = commands_stub

    stubs = {
        "modules.AI_manager": ai_manager_stub,
        "modules.channel_policies": channel_policies_stub,
        "modules.bot_whitelist": _load_bot_whitelist(),
        "modules.utils": utils_stub,
        "discord": discord_stub,
        "discord.ext": discord_ext_stub,
        "discord.ext.commands": commands_stub,
    }
    originals = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _censor_message(message, banned_words):
    # Mirrors modules.utils.censor_message so assertions exercise real censoring
    return re.sub(
        "|".join([re.escape(word) for word in banned_words]),
        lambda m: "#" * len(m.group()),
        message,
        flags=re.IGNORECASE,
    )


class _Config:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, **values):
        self.values.update(values)


class _LiveManager:
    def __init__(self, **config):
        self.config = _Config(**config)


class _ExplodingManager:
    @property
    def config(self):
        raise RuntimeError("manager not initialized")


class ChatCensorHotReloadTests(unittest.TestCase):
    MESSAGE = "well stfu then"

    @classmethod
    def setUpClass(cls):
        cls.chat_module = _load_chat_module()

    def setUp(self):
        self.chat_module.AI_Manager.M.MANAGER = None
        self.chat_module.CONTEXT.plugin_config["censor"] = True

    def tearDown(self):
        self.chat_module.AI_Manager.M.MANAGER = None

    def censor_with_live_manager(self, manager):
        module = self.chat_module
        module.AI_Manager.M.MANAGER = manager
        return module.censor_chat(None, "chan-1", "User", "alice", self.MESSAGE)

    def test_hot_reloaded_false_on_live_config_beats_stale_plugin_config(self):
        result = self.censor_with_live_manager(_LiveManager(censor=False))

        self.assertEqual(result, ("chan-1", "User", "alice", self.MESSAGE, None))

    def test_live_config_censors_banned_words_when_enabled(self):
        result = self.censor_with_live_manager(_LiveManager(censor=True))

        self.assertEqual(result[3], "well #### then")

    def test_missing_manager_falls_back_to_plugin_config(self):
        result = self.chat_module.censor_chat(
            None, "chan-1", "User", "alice", self.MESSAGE
        )

        self.assertEqual(result[3], "well #### then")

    def test_raising_manager_falls_back_to_plugin_config(self):
        result = self.censor_with_live_manager(_ExplodingManager())

        self.assertEqual(result[3], "well #### then")

    def test_fallback_respects_plugin_config_disabled(self):
        self.chat_module.CONTEXT.plugin_config["censor"] = False
        try:
            result = self.chat_module.censor_chat(
                None, "chan-1", "User", "alice", self.MESSAGE
            )
        finally:
            self.chat_module.CONTEXT.plugin_config["censor"] = True

        self.assertEqual(result[3], self.MESSAGE)

    def test_provider_prompt_is_censored_when_enabled(self):
        result = self.censor_with_live_manager(_LiveManager(censor=True))

        self.assertEqual(
            self.chat_module._censor_for_provider(self.MESSAGE),
            result[3],
        )

    def test_provider_prompt_stays_uncensored_when_disabled(self):
        result = self.censor_with_live_manager(_LiveManager(censor=False))

        self.assertEqual(self.chat_module._censor_for_provider(self.MESSAGE), self.MESSAGE)


if __name__ == "__main__":
    unittest.main()
