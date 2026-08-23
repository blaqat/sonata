import importlib.util
import pathlib
import sys
import types
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest import mock

import discord

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
VOICE_PATH = REPO_ROOT / "src" / "modules" / "plugins" / "voice.py"


def load_voice_module():
    spec = importlib.util.spec_from_file_location("voice_plugin_test", VOICE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load voice plugin module")

    class StubManager:
        @staticmethod
        def builder(func):
            return func

        @staticmethod
        def with_context(**_kwargs):
            return lambda func: func

    class StubPromptManager:
        def add(self, *_args, **_kwargs):
            return None

    manager = StubManager()
    prompt_manager = StubPromptManager()
    ai_manager_stub = types.ModuleType("modules.AI_manager")
    ai_manager_stub.AI_Manager = type(
        "AIManagerStub",
        (),
        {
            "init": staticmethod(
                lambda *_args, **_kwargs: (
                    SimpleNamespace(),
                    manager,
                    prompt_manager,
                )
            )
        },
    )
    utils_stub = types.ModuleType("modules.utils")
    utils_stub.async_cprint = lambda *_args, **_kwargs: None
    utils_stub.async_print = lambda *_args, **_kwargs: None
    stubs = {
        "modules.AI_manager": ai_manager_stub,
        "modules.utils": utils_stub,
    }
    originals = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    return module


voice_plugin = load_voice_module()


class FakeConfig:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, **values):
        self.values.update(values)


class FakeVoiceClient:
    def __init__(self, channel=None, connected=True):
        self.channel = channel
        self.connected = connected
        self.disconnect_calls = []
        self.move_calls = []

    def is_connected(self):
        return self.connected

    async def disconnect(self, *, force=False):
        self.disconnect_calls.append(force)
        self.connected = False

    async def move_to(self, channel):
        self.move_calls.append(channel)
        self.channel = channel


class FakeChannel:
    def __init__(self, *connect_results):
        self.connect_results = list(connect_results)
        self.connect_calls = 0

    async def connect(self):
        self.connect_calls += 1
        result = self.connect_results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class FakeGuild:
    def __init__(self, voice_client=None):
        self.voice_client = voice_client


class FakeContext:
    def __init__(self, guild, channel=None, ctx_id=1):
        self.guild = guild
        self.id = ctx_id
        self.author = SimpleNamespace(
            voice=None if channel is None else SimpleNamespace(channel=channel)
        )
        self.message = SimpleNamespace(guild=guild)
        self.sent = []
        self.replies = []

    async def send(self, message):
        self.sent.append(message)

    async def reply(self, message):
        self.replies.append(message)


class FakeManager:
    def __init__(self, **config):
        self.config = FakeConfig(**config)
        self.chat = SimpleNamespace(
            send=mock.Mock(),
            request=mock.Mock(return_value="response"),
        )
        self.prompt_manager = SimpleNamespace(get=mock.Mock(return_value="voice prompt"))


class VoicePluginTests(unittest.IsolatedAsyncioTestCase):
    def service(self, *, speaking=True, recording=False, **config):
        manager = FakeManager(**config)
        runtime = SimpleNamespace(vc_speaking=speaking, vc_recording=recording)
        return voice_plugin.VoiceService(manager, runtime), manager

    async def test_respond_honors_speaking_disable_before_connecting(self):
        service, manager = self.service(speaking=False)
        target = FakeChannel(FakeVoiceClient())
        context = FakeContext(FakeGuild(), target)

        await service.respond(context)

        self.assertEqual(context.sent, ["soz voice speaking is disabled"])
        self.assertEqual(target.connect_calls, 0)
        manager.chat.request.assert_not_called()

    async def test_respond_runs_chat_request_off_the_event_loop(self):
        active_client = FakeVoiceClient()
        service, manager = self.service()
        context = FakeContext(FakeGuild(active_client), ctx_id=42)
        service.say = mock.AsyncMock()

        with mock.patch.object(
            voice_plugin.asyncio, "to_thread", new=mock.AsyncMock(return_value="hello")
        ) as to_thread:
            await service.respond(context)

        to_thread.assert_awaited_once_with(
            manager.chat.request,
            42,
            "Respond to the context based on the chat log",
            "System",
            None,
            AI="OpenAI",
            instructions=voice_plugin.VOICE_INSTRUCTIONS,
        )
        service.say.assert_awaited_once_with(active_client, "hello")

    async def test_talk_ignores_cached_client_from_another_guild(self):
        service, _ = self.service()
        other_guild_client = FakeVoiceClient()
        service.current_vc = other_guild_client
        current_guild_client = FakeVoiceClient()
        target = FakeChannel(current_guild_client)
        context = FakeContext(FakeGuild(), target)
        service.say = mock.AsyncMock()

        await service.talk(context, "hello")

        self.assertEqual(target.connect_calls, 1)
        service.say.assert_awaited_once_with(
            current_guild_client,
            "hello",
            {"voice": "nova"},
        )

    async def test_voice_callback_uses_selected_voice(self):
        service, manager = self.service(vc_voice="shimmer")
        service.start_recording = mock.AsyncMock()
        service.say = mock.AsyncMock()
        member = SimpleNamespace(id=7, nick="Karma", name="Karma")
        channel = SimpleNamespace(
            guild=SimpleNamespace(fetch_member=mock.AsyncMock(return_value=member))
        )
        voice_client = FakeVoiceClient(channel=SimpleNamespace(id=99))
        sink = SimpleNamespace(
            vc=voice_client,
            audio_data={7: SimpleNamespace(file=BytesIO(b"a" * 60001))},
        )
        fake_openai = SimpleNamespace(
            audio=SimpleNamespace(
                transcriptions=SimpleNamespace(
                    create=mock.Mock(return_value=SimpleNamespace(text="sonata hello"))
                )
            )
        )

        with (
            mock.patch.object(voice_plugin, "openai", fake_openai),
            mock.patch.object(
                voice_plugin.asyncio,
                "to_thread",
                new=mock.AsyncMock(return_value="sonata hi"),
            ),
        ):
            await service.vc_callback(sink, channel)

        service.say.assert_awaited_once_with(
            voice_client,
            "Karma: hi",
            {"voice": "shimmer"},
        )
        manager.chat.send.assert_called_once_with(99, "User", "Karma", "sonata hello")

    async def test_voice_callback_does_not_restart_after_disconnect(self):
        service, _ = self.service()
        service.start_recording = mock.AsyncMock()
        voice_client = FakeVoiceClient(connected=False)
        sink = SimpleNamespace(vc=voice_client, audio_data={})
        channel = SimpleNamespace(guild=SimpleNamespace())

        await service.vc_callback(sink, channel)

        service.start_recording.assert_not_awaited()
        self.assertTrue(service.is_ready)

    async def test_join_only_recovers_disconnected_stale_clients(self):
        stale_client = FakeVoiceClient(connected=False)
        replacement = FakeVoiceClient()
        target = FakeChannel(discord.ClientException("Already connected"), replacement)
        service, _ = self.service()
        context = FakeContext(FakeGuild(stale_client), target)

        await service.join(context)

        self.assertEqual(stale_client.disconnect_calls, [True])
        self.assertEqual(target.connect_calls, 2)
        self.assertIs(service.current_vc, replacement)

    async def test_join_propagates_unexpected_connection_failures(self):
        target = FakeChannel(RuntimeError("Missing permissions"))
        service, _ = self.service()
        context = FakeContext(FakeGuild(), target)

        with self.assertRaisesRegex(RuntimeError, "Missing permissions"):
            await service.join(context)

        self.assertEqual(target.connect_calls, 1)

    async def test_leave_clears_cached_client_and_allows_already_disconnected(self):
        client = FakeVoiceClient()
        service, _ = self.service()
        service.current_vc = client
        await service.leave(FakeContext(FakeGuild(client)))

        self.assertEqual(client.disconnect_calls, [False])
        self.assertIsNone(service.current_vc)

        await service.leave(FakeContext(FakeGuild()))
