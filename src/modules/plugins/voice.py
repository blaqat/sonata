"""
Voice
-----
Voice-channel recording, transcription, response generation, and TTS playback.

The plugin owns the Discord voice commands and listener registration so the bot
entry point does not need to know about voice-specific state or OpenAI audio
operations.
"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

import discord
import openai

from modules.AI_manager import AI_Manager
from modules.utils import async_cprint as cprint
from modules.utils import async_print as print

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(lazy=True)
__plugin_name__ = "voice"
__dependencies__ = ["chat"]


VOICE_INSTRUCTIONS = """
You're Discord voice chat bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user.

Response Guidelines:
- MOST IMPORTANT: Analyze the chat log and try to match the vibe and way of speaking of the users in the chat.

- Short and brief
- Simple language
- Smart aleck, know-it-all attitude
- Humor encouraged, no corny jokes
- Swearing allowed (18+ server)
- In voice chat so responses should be speakable
  - express through punctiuation, repeated characters and capsas these control your voice
- Don't only be mean, be a little silly and friendly *sometimes* too

Attributes:
- Dislikes: corny jokes, being told what to do
- Hates: furries, loud music
- Gender: Female, feminine
"""

VALID_VOICES = (
    "alloy",
    "ash",
    "coral",
    "echo",
    "fable",
    "onyx",
    "sage",
    "nova",
    "shimmer",
)

CONNECT_TIMEOUT = 15

PROMPT_MANAGER.add("VoiceInstructions", VOICE_INSTRUCTIONS)


def _runtime_flag(runtime: Any, name: str, default: bool) -> bool:
    if runtime is None:
        return default
    if isinstance(runtime, dict):
        return bool(runtime.get(name, default))
    return bool(getattr(runtime, name, default))


def _member_name(user: Any) -> str | None:
    return getattr(user, "nick", None) or getattr(user, "name", None)


class VoiceService:
    """Runtime voice functionality bound to the live Sonata manager."""

    def __init__(self, manager: AI_Manager, runtime: Any = None):
        self.manager = manager
        self.runtime = runtime
        self.bot = None
        self.current_vc: discord.VoiceClient | None = None
        self.speaking_mutex = asyncio.Lock()
        self.is_ready = True

    def speaking_enabled(self) -> bool:
        return _runtime_flag(self.runtime, "vc_speaking", True)

    def recording_enabled(self) -> bool:
        return _runtime_flag(self.runtime, "vc_recording", False)

    def _active_voice_client(self, guild):
        """Return the connected voice client for this guild, if one exists."""
        voice_client = getattr(guild, "voice_client", None)
        if voice_client is not None and voice_client.is_connected():
            self.current_vc = voice_client
            return voice_client

        # The service can receive commands from several guilds. Do not reuse a
        # cached client unless Discord confirms it belongs to this live guild.
        self.current_vc = None
        return None

    async def _connect_to_channel(self, guild, channel):
        """Connect to a channel, recovering only a disconnected stale client."""
        try:
            voice_client = await channel.connect(timeout=CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            return None
        except discord.ClientException:
            stale_client = getattr(guild, "voice_client", None)
            if stale_client is None or stale_client.is_connected():
                return None
            try:
                await stale_client.disconnect(force=True)
                voice_client = await channel.connect(timeout=CONNECT_TIMEOUT)
            except (asyncio.TimeoutError, discord.ClientException):
                return None

        self.current_vc = voice_client
        return voice_client

    async def _get_or_connect_voice_client(self, ctx):
        voice_client = self._active_voice_client(ctx.guild)
        if voice_client is not None:
            return voice_client

        voice_state = getattr(ctx.author, "voice", None)
        if voice_state is None or getattr(voice_state, "channel", None) is None:
            await ctx.send("You are not in a voice channel.")
            return None

        voice_client = await self._connect_to_channel(ctx.guild, voice_state.channel)
        if voice_client is None:
            await ctx.send("I couldn't join your voice channel.")
        return voice_client

    async def say(self, vc: discord.VoiceClient, message: str, opts: dict | None = None):
        """Synthesize and play a message while the bot is in a voice channel."""
        opts = opts or {}
        try:
            audio_bytes: bytes = await asyncio.to_thread(
                lambda: openai.audio.speech.create(
                    model="tts-1",
                    voice=opts.get("voice", "sage"),
                    input=message,
                    response_format="opus",
                ).read()
            )
        except Exception as exc:
            cprint(f"Error on openai: {exc}", "red")
            return

        if not vc.is_connected():
            return

        buffer = BytesIO(audio_bytes)

        cprint(f"Playing audio: {message}", "green")
        try:
            vc.play(discord.FFmpegOpusAudio(buffer, pipe=True))
        except discord.ClientException:
            return
        while vc.is_playing():
            await asyncio.sleep(1)

    async def vc_callback(
        self, sink: discord.sinks, channel: discord.TextChannel, *args
    ):
        """Process recorded voice audio and continue the recording loop."""
        del args
        self.is_ready = False
        try:
            recorded_users = [
                await channel.guild.fetch_member(int(user_id))
                for user_id, _ in sink.audio_data.items()
            ]

            for user in recorded_users:
                name = _member_name(user)
                if name is None:
                    continue

                sink_data = sink.audio_data.get(user.id)
                if sink_data is None:
                    continue

                data: BytesIO = sink_data.file
                data.seek(0)
                data.name = "audio.mp3"

                # Ignore recordings that are too short to transcribe usefully.
                if len(data.read()) <= 60000:
                    continue
                data.seek(0)

                cprint(f"Transcribing audio from {name}...", "blue")
                transcription = await asyncio.to_thread(
                    openai.audio.transcriptions.create,
                    file=data,
                    model="whisper-1",
                    prompt="Your name is Sonata",
                )
                words = transcription.text.lower()

                channel_id = sink.vc.channel.id
                self.manager.chat.send(channel_id, "User", name, words)

                command = words if "sonata" in words else None
                if not command:
                    continue

                cprint(f"{name}: {words}", "cyan")
                response = await asyncio.to_thread(
                    self.manager.chat.request,
                    channel_id,
                    command,
                    name,
                    AI="OpenAI",
                    instructions=self.manager.prompt_manager.get("VoiceInstructions"),
                )
                if response.strip().startswith("sonata"):
                    response = response.split("sonata", 1)[1].strip()
                response = f"{name}: {response}"

                if not self.speaking_enabled():
                    continue

                async with self.speaking_mutex:
                    await self.say(
                        sink.vc,
                        response,
                        {"voice": self.manager.config.get("vc_voice", "nova")},
                    )
        except Exception as exc:
            cprint(exc, "red")
        finally:
            self.is_ready = True

        # The recording callback can finish after its voice client disconnects.
        # Do not schedule a new loop for a client that can no longer record.
        if self.recording_enabled() and sink.vc.is_connected():
            await self.start_recording(sink.vc, channel)

    async def start_recording(self, vc: discord.VoiceClient, channel: discord.TextChannel):
        try:
            print("Starting recording")
            for _ in range(10):
                if vc.is_connected():
                    break
                await asyncio.sleep(1)
            else:
                return
            vc.start_recording(discord.sinks.MP3Sink(), self.vc_callback, channel)
            await asyncio.sleep(8)
            print("Stopping recording")
            vc.stop_recording()
        except Exception as exc:
            print(f"Error: {exc}")

    async def on_voice_state_update(self, member, before, after):
        """Start or restart recording when Sonata joins or changes channels."""
        bot_user = getattr(self.bot, "user", None)
        if bot_user is None or member.id != bot_user.id:
            return

        if before.channel is None and after.channel is not None:
            print(f"Sonata has joined the voice channel: {after.channel.name}")
            vc = member.guild.voice_client
            if self.recording_enabled():
                await self.start_recording(vc, after.channel)
            else:
                cprint("VC Recording is disabled", "red")
        elif before.channel is not None and after.channel is None:
            print(f"Sonata has left the voice channel: {before.channel.name}")
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            print(
                f"Sonata has moved from {before.channel.name} to {after.channel.name}"
            )
            vc = member.guild.voice_client
            if self.recording_enabled():
                await self.start_recording(vc, after.channel)
            else:
                cprint("VC Recording is disabled", "red")

    async def respond(self, ctx):
        """Respond in the current voice channel using the chat context."""
        if not self.speaking_enabled():
            return await ctx.send("soz voice speaking is disabled")

        vc = await self._get_or_connect_voice_client(ctx)
        if vc is None:
            return

        response = await asyncio.to_thread(
            self.manager.chat.request,
            ctx.channel.id,
            "Respond to the context based on the chat log",
            "System",
            None,
            AI="OpenAI",
            instructions=VOICE_INSTRUCTIONS,
        )

        async with self.speaking_mutex:
            await self.say(
                vc,
                response,
                {"voice": self.manager.config.get("vc_voice", "nova")},
            )

    async def voice(self, ctx, *voice):
        """Change or display the voice used for TTS in voice channels."""
        if not self.speaking_enabled():
            return await ctx.send("soz voice speaking is disabled")

        selected_voice = " ".join(voice).lower()
        if selected_voice == "":
            await ctx.send(
                f"Current voice is `{self.manager.config.get('vc_voice', 'nova')}`. "
                f"Valid options are: `{', '.join(VALID_VOICES)}`"
            )
            return

        if selected_voice not in VALID_VOICES:
            await ctx.send(
                f"Invalid voice option. Valid options are: {', '.join(VALID_VOICES)}"
            )
            return

        self.manager.config.set(vc_voice=selected_voice)
        await ctx.send(f"Voice changed to {selected_voice}")

    async def talk(self, ctx, *message):
        """Join the author's voice channel if needed and speak a message."""
        if not self.speaking_enabled():
            return await ctx.send("soz voice speaking is disabled")

        vc = await self._get_or_connect_voice_client(ctx)
        if vc is None:
            return

        message_text = " ".join(message)
        if message_text:
            await self.say(
                vc,
                message_text,
                {"voice": self.manager.config.get("vc_voice", "nova")},
            )

    async def join(self, ctx):
        """Join the author's voice channel."""
        voice_state = getattr(ctx.author, "voice", None)
        if voice_state is None or getattr(voice_state, "channel", None) is None:
            return await ctx.reply("You are not in a voice channel.")

        voice_client = self._active_voice_client(ctx.guild)
        if voice_client is not None:
            if voice_client.channel != voice_state.channel:
                await voice_client.move_to(voice_state.channel)
            self.current_vc = voice_client
            return

        voice_client = await self._connect_to_channel(ctx.guild, voice_state.channel)
        if voice_client is None:
            await ctx.send("I couldn't join your voice channel.")

    async def leave(self, ctx):
        """Leave the current voice channel."""
        voice_client = getattr(ctx.message.guild, "voice_client", None)
        if voice_client is None:
            return

        await voice_client.disconnect()
        if self.current_vc is voice_client:
            self.current_vc = None

    def register(self, bot) -> None:
        """Register voice commands and the voice-state listener exactly once."""
        if getattr(bot, "_sonata_voice_registered", False):
            return

        self.bot = bot

        def register_command(name: str, handler) -> None:
            if bot.get_command(name) is None:
                bot.command(name=name)(handler)

        async def respond_command(ctx):
            return await self.respond(ctx)

        async def voice_command(ctx, *voice):
            return await self.voice(ctx, *voice)

        async def talk_command(ctx, *message):
            return await self.talk(ctx, *message)

        async def join_command(ctx):
            return await self.join(ctx)

        async def leave_command(ctx):
            return await self.leave(ctx)

        register_command("respond", respond_command)
        register_command("voice", voice_command)
        register_command("talk", talk_command)
        register_command("join", join_command)
        register_command("leave", leave_command)

        if not getattr(bot, "_sonata_voice_listener_registered", False):
            async def voice_state_listener(member, before, after):
                return await self.on_voice_state_update(member, before, after)

            bot.listen("on_voice_state_update")(voice_state_listener)
            bot._sonata_voice_listener_registered = True

        bot._sonata_voice_registered = True


@MANAGER.builder
def voice(sonata: AI_Manager):
    class BoundVoiceService(VoiceService):
        def __init__(self):
            super().__init__(sonata, getattr(sonata, "runtime_config", None))

    return BoundVoiceService


@MANAGER.with_context(manager=True, client=True)
def register_voice(context):
    context.manager.voice.register(context.client)
