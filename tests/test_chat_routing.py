import ast
import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


def _load_chat_module():
    module_path = SRC_ROOT / "modules" / "plugins" / "chat.py"
    spec = importlib.util.spec_from_file_location("chat_plugin_test", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load chat module spec")

    class _Manager:
        MANAGER = types.SimpleNamespace(config={})

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

    class _AIManager:
        @staticmethod
        def init(*_args, **_kwargs):
            return context, manager, prompt_manager

    ai_manager_stub = types.ModuleType("modules.AI_manager")
    ai_manager_stub.AI_Manager = _AIManager
    ai_manager_stub.Context = object

    channel_policies_stub = types.ModuleType("modules.channel_policies")
    channel_policies_stub.LEGACY_CHANNEL_BLACKLIST = set()
    channel_policies_stub.ChannelPolicies = object
    channel_policies_stub.get_channel_policy = lambda *_args, **_kwargs: {}
    channel_policies_stub.get_command_name = lambda content: (
        content.split(maxsplit=1)[0].lstrip("$") if content.startswith("$") else None
    )

    async def _get_reference(message):
        return message.resolved_reference

    async def _get_reference_chain(message, **_kwargs):
        return message

    utils_stub = types.ModuleType("modules.utils")
    utils_stub.censor_message = lambda message, _words: message
    utils_stub.async_print = lambda *_args, **_kwargs: None
    utils_stub.async_cprint = lambda *_args, **_kwargs: None
    utils_stub.cstr = lambda **kwargs: kwargs["str"]
    utils_stub.classify_ai_error = lambda _error: ("internal", "something went wrong")
    utils_stub.TRANSIENT_AI_ERRORS = {"rate_limit", "timeout", "server_error"}
    utils_stub.get_full_name = lambda message: message.author.name
    utils_stub.setter = lambda *_args, **_kwargs: None
    utils_stub.settings = types.SimpleNamespace(TENOR_G="", KLIPY="")
    utils_stub.has_inside = lambda *_args, **_kwargs: False
    utils_stub.get_reference_message = _get_reference
    utils_stub.get_reference_chain = _get_reference_chain
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


class _Config:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class _PolicyManager:
    def __init__(self, respond_all=False):
        self.respond_all = respond_all

    def can_speak(self, **_kwargs):
        return True

    def is_command_allowed(self, **_kwargs):
        return True

    def should_respond_all(self, **_kwargs):
        return self.respond_all

    def is_protected(self, **_kwargs):
        # Chat routing tests focus on rewriting/routing decisions, not privacy
        # encryption behavior. Default to unprotected.
        return False


class _Chat:
    def __init__(self, respond_all=False):
        self.policy_manager = _PolicyManager(respond_all)
        self.saved = []

    def send(self, *args):
        self.saved.append(args)


class _Message:
    def __init__(self, content, reference=None):
        self.content = content
        self.author = types.SimpleNamespace(
            bot=False,
            name="alice",
            nick=None,
            id=7,
            roles=[],
            color=None,
        )
        self.guild = types.SimpleNamespace(id=1, name="Guild")
        self.channel = types.SimpleNamespace(id=2, name="general")
        self.attachments = []
        self.resolved_reference = reference
        self.replies = []

    async def reply(self, content, **kwargs):
        self.replies.append((content, kwargs))


class _Bot:
    def __init__(self):
        self.user = types.SimpleNamespace(id=99)
        self.current_guild = ""
        self.current_channel = ""
        self.processed = []

    async def process_commands(self, message, **kwargs):
        self.processed.append((message.content, kwargs))


class ChatHookRoutingTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.chat_module = _load_chat_module()

    async def _run_hook(self, content, *, reference=None, respond_all=False):
        sonata = types.SimpleNamespace(
            config=_Config(
                auto="c",
                censor=False,
                view_replies=True,
                ignore=[],
                bot_whitelist=[],
                response_map={"alice": [1, "obsolete response"]},
            ),
            chat=_Chat(respond_all),
            get=lambda *_args, **_kwargs: None,
        )
        bot = _Bot()
        message = _Message(content, reference)
        await self.chat_module.chat_hook(sonata, bot, message)
        return sonata, bot, message

    async def test_direct_mention_preserves_trailing_digit(self):
        sonata, bot, message = await self._run_hook("Sonata keep this 1")

        self.assertEqual(bot.processed[0][0], "$c keep this 1")
        self.assertEqual(message.replies, [])
        self.assertFalse(
            any(entry[1] == "Bot" for entry in sonata.chat.saved),
            "legacy predefined responses must not be emitted",
        )

    async def test_reply_to_sonata_preserves_trailing_digit(self):
        reference = types.SimpleNamespace(author=types.SimpleNamespace(id=99))
        _, bot, _ = await self._run_hook("keep this 0", reference=reference)

        self.assertEqual(bot.processed[0][0], "$c keep this 0")

    async def test_respond_all_preserves_trailing_digit(self):
        _, bot, _ = await self._run_hook("keep this 1", respond_all=True)

        self.assertEqual(bot.processed[0][0], "$c keep this 1")

    async def test_explicit_command_is_not_rewritten(self):
        _, bot, _ = await self._run_hook("$c keep this 0")

        self.assertEqual(bot.processed[0][0], "$c keep this 0")

    async def test_leading_command_with_wake_keyword_stays_command(self):
        _, bot, _ = await self._run_hook("$help sonata")

        self.assertEqual(bot.processed[0][0], "$help sonata")

    async def test_leading_command_with_sona_keyword_stays_command(self):
        _, bot, _ = await self._run_hook("$play foo sona")

        self.assertEqual(bot.processed[0][0], "$play foo sona")

    async def test_reply_to_sonata_with_leading_command_stays_command(self):
        reference = types.SimpleNamespace(author=types.SimpleNamespace(id=99))
        _, bot, _ = await self._run_hook("$help", reference=reference)

        self.assertEqual(bot.processed[0][0], "$help")

    async def test_reply_to_sonata_plain_text_still_ai(self):
        reference = types.SimpleNamespace(author=types.SimpleNamespace(id=99))
        _, bot, _ = await self._run_hook("hello there", reference=reference)

        self.assertEqual(bot.processed[0][0], "$c hello there")

    async def test_keyword_first_with_embedded_command_stays_ai(self):
        _, bot, _ = await self._run_hook("sonata $help")

        self.assertEqual(bot.processed[0][0], "$c $help")

    async def test_keyword_first_play_stays_ai(self):
        _, bot, _ = await self._run_hook("sona $play something")

        self.assertEqual(bot.processed[0][0], "$c $play something")

    async def test_keyword_only_still_ai(self):
        _, bot, _ = await self._run_hook("hey sonata what is up")

        self.assertEqual(bot.processed[0][0], "$c hey  what is up")

    async def test_own_bot_message_is_mirrored_and_not_processed(self):
        mirrored = []
        sonata, bot, message = await self._run_hook("Set `chat.protected` → `allow`")
        bot.processed.clear()
        message.author.id = bot.user.id
        message.author.bot = True
        message.author.name = "mideration team"
        sonata.get = (
            lambda key, val="value", default=None, inner=True: (
                (lambda _s, msg: mirrored.append(msg.content))
                if key == "termcmd" and val == "mirror_own_message"
                else default
            )
        )
        await self.chat_module.chat_hook(sonata, bot, message)
        self.assertEqual(bot.processed, [])
        self.assertEqual(mirrored, ["Set `chat.protected` → `allow`"])

    async def test_own_bot_message_skips_mirror_when_protected(self):
        mirrored = []
        sonata, bot, message = await self._run_hook("secret")
        bot.processed.clear()
        sonata.chat.policy_manager.is_protected = lambda **_kwargs: True
        message.author.id = bot.user.id
        message.author.bot = True
        sonata.get = (
            lambda key, val="value", default=None, inner=True: (
                (lambda _s, msg: mirrored.append(msg.content))
                if key == "termcmd" and val == "mirror_own_message"
                else default
            )
        )
        await self.chat_module.chat_hook(sonata, bot, message)
        self.assertEqual(bot.processed, [])
        self.assertEqual(mirrored, [])


def _load_ai_question():
    source = (SRC_ROOT / "index.py").read_text()
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "ai_question"
    )
    namespace = {"RESPONSE_FAILURES": {}, "MAX_FAILURES": 3}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "src/index.py", "exec"), namespace)
    return namespace["ai_question"], namespace


class _Typing:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class AIQuestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_question_preserves_final_zero_and_one_and_replies(self):
        ai_question, namespace = _load_ai_question()
        requests = []
        replies = []
        channel = types.SimpleNamespace(id=12)

        class _RuntimeConfig:
            def set(self, **_kwargs):
                pass

            def get(self, _key, default=None):
                return default

        class _RuntimeChat:
            def request(self, _channel_id, message, *_args, **_kwargs):
                requests.append(message)
                return "answer"

            def send(self, *_args):
                pass

        sonata = types.SimpleNamespace(
            config=_RuntimeConfig(),
            chat=_RuntimeChat(),
            name="Sonata",
            get=lambda *_args, **_kwargs: None,
        )
        ctx = types.SimpleNamespace(typing=lambda: _Typing(), message=object())

        async def get_channel(_ctx):
            return channel

        async def ctx_reply(*args):
            replies.append(args)

        namespace.update(
            {
                "Sonata": sonata,
                "asyncio": asyncio,
                "get_channel": get_channel,
                "get_full_name": lambda _ctx: "alice",
                "get_chain": lambda _message: None,
                "ctx_reply": ctx_reply,
                "cprint": lambda *_args, **_kwargs: None,
                "print": lambda *_args, **_kwargs: None,
                "get_trace": lambda: "",
                "ordinal": lambda value: str(value),
                "settings": types.SimpleNamespace(GOD=1),
                "restart": lambda: None,
            }
        )

        for content in ("natural 0", "natural 1"):
            await ai_question(ctx, content, ai="Claude", short="c")

        self.assertEqual(requests, ["natural 0", "natural 1"])
        self.assertEqual(replies, [(ctx, "answer"), (ctx, "answer")])


if __name__ == "__main__":
    unittest.main()
