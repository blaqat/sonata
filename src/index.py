"""
_____________________________________________________

 .M'"'bgd                              mm
,MI    "Y                              MM
`MMb.      ,pW"Wq.`7MMpMMMb.   ,6"Yb.mmMMmm  ,6"Yb.
  `YMMNq. 6W'   `Wb MM    MM  8)   MM  MM   8)   MM
.     `MM 8M     M8 MM    MM   ,pm9MM  MM    ,pm9MM
Mb     dM YA.   ,A9 MM    MM  8M   MM  MM   8M   MM
P"Ybmmd"   `Ybmd9'.JMML  JMML.`Moo9^Yo.`Mbmo`Moo9^Yo.

               a discord bot by @blaqat
_____________________________________________________
"""

"""
Test Configuration
"""
# TODO: Move configuration to a separate file
RANDOM_CONFIG = False
AUTO_MODEL = "c"  # g, o, c, a, m
PROMPT_RESET = False
VC_RECORDING = False
VC_SPEAKING = True
GIF_SEARCH = "random"  # tenor, giphy, google, random
EMOJIS = False
AGENT = False  # Removes ability to run single commands other than agent
IGNORE_LIST = []


def rand_config():
    global AUTO_MODEL, PROMPT_RESET, VC_RECORDING, VC_SPEAKING, GIF_SEARCH, EMOJIS, AGENT
    models = ["g", "o", "c", "a", "m"]
    gif_searches = ["tenor", "giphy", "google", "random"]
    AUTO_MODEL = models[randint(0, len(models) - 1)]
    PROMPT_RESET = bool(randint(0, 1))
    VC_RECORDING = bool(randint(0, 1))
    VC_SPEAKING = bool(randint(0, 1))
    GIF_SEARCH = gif_searches[randint(0, len(gif_searches) - 1)]
    EMOJIS = bool(randint(0, 1))
    AGENT = bool(randint(0, 1))


import asyncio
import base64
import os
import re
from io import BytesIO
from random import randint
import sys

import aioconsole
import anthropic
import discord

import google.generativeai as genai
import openai
import requests
from discord.ext import commands

from PIL import Image

from modules.AI_manager import AI_Error, AI_Manager, PromptManager
from modules.plugins import PLUGINS
from modules.utils import async_cprint as cprint, async_print as print, RestartSignal
from modules.utils import (
    get_full_name,
    settings,
    get_reference_chain as get_chain,
    get_trace,
    ordinal,
)

import nest_asyncio

nest_asyncio.apply()

if not discord.opus.is_loaded():
    # The 'libopus.so' path might need to be adjusted based on your installation
    # discord.opus.load_opus("/usr/lib/x86_64-linux-gnu/libopus.so")
    discord.opus.load_opus("/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.0.dylib")


PROMPT = """
As "sonata", a Discord bot created by blaqat and :sparkles:"powered by AI":sparkles:™️, your role is to engage with users.
- You are a general expert on most subjects including math, coding, doctor, etc.
- Adopt a friendly and normal tone.
- Keep responses brief, possibly with a touch of humor.
- Only provide the response message without additional text or quote symbols.
- Respond in the language of the person you are replying to.
"""

PROMPT_MANAGER = PromptManager(instructions=lambda *a: PROMPT.format(*a))


def reset_instructions():
    """
    Reset and install the default instruction templates on the global P object.
    """
    PROMPT_MANAGER.set_instructions(lambda *a: PROMPT.format(*a))
    PROMPT_MANAGER.add(
        "Message",
        lambda user, msg, responding_to: "message chain:\n{2}\nnew message: {0}: {1}".format(
            user, msg, responding_to
        ),
    )
    PROMPT_MANAGER.add(
        "MessageAssistant",
        lambda user, msg: "{0}: {1}".format(user, msg),
    )
    PROMPT_MANAGER.add(
        "History",
        lambda history: f"""Here is the chat history so far BEGINING :: {
            history} :: END
""",
    )

    PROMPT_MANAGER.add("DefaultInstructions", lambda *a: PROMPT.format(*a))


reset_instructions()


# TODO: Add specific events for on_load, on_message, on_exit, etc
# - Specifically connect to Chat hooks (on_message) and Term Command Saving (on_exit)
#  https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645122
Sonata, MANAGER = AI_Manager.init(
    PROMPT_MANAGER,
    "Gemini",
    (settings.GOOGLE_AI, "Gemini", 1, 2500),
    summarize_chat=True,
    name="Sonata",
)

Sonata.config.set(temp=1)
Sonata.config.setup()


@MANAGER.prompt
def ExplainBlockReasoning(r, user):
    return f"""You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}
Here is the prompt_feedback: {r}
"""


# TODO: Add task manager plugin
# - Can handle a queue of async or sequential tasks
# - Can pass in requested Manager/Clients as arguments to task function
# - This more easily allows scope access to other plugins
# - Like self-command cant have a join vc command since it needs to be async and have access to the client
# https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645203
def extend(Sonata):
    """
    Extends the Sonata AI_Manager with additional plugins and configurations.
    """
    # Add funny responses with a small chance of being triggered
    # TODO: Move to configuration
    funny_responses = {
        "subi": (
            0.005,
            "i dont know but can you play piano for me? <a:kittypleading:1213940324658057236>",
        ),
        "log": (0.005, "BWAAAAAAAA BWAAAAAA BWAAAAAAAAAAAAA"),
        "blaqat": (0.005, "yes master"),
        "ans": (0.01, "youre the robot why dont u tell me hmmm?"),
    }

    # TODO: Move config to configuration
    Sonata.extend(
        PLUGINS(openai_assistant=False),
        chat={
            "summarize": True,
            "max_chats": 30,
            "view_replies": True,
            "auto": AUTO_MODEL,
            "ignore": [name.lower() for name in IGNORE_LIST],
            "response_map": funny_responses,
            "bot_whitelist": [
                "BluBot",
                1311742291521835048,
                746799398994051162,
            ],
            "censor": False,
        },
        self_commands={"gif_search": GIF_SEARCH, "agent": AGENT},
        term_commands={
            "inject_emojis": EMOJIS,
        },
    )


# -------------------------------------------------------------------
# AI Model Registerings
# -------------------------------------------------------------------


@MANAGER.register_ai(
    client=openai.images,
    default=False,
    key=settings.OPEN_AI,
    setup=lambda _, key: setattr(openai, "api_key", key),
    model="dall-e-3",
    # model="dall-e-2",
    # model = "gpt-image-1"
)
def DallE(client, prompt, model, config):
    return (
        client.generate(
            model=model,
            prompt=prompt,
            # quality=config.get("quality", "auto"),
            quality=config.get("quality", "standard"),
            n=config.get("num_images", 1),
        )
        .data[0]
        .url
    )


@MANAGER.register_ai(
    client=openai,
    default=False,
    key=settings.OPEN_AI,
    setup=lambda _, k: True,
    model="gpt-4o",
)
def Assistant(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    i = config.get("images", False)
    if i:
        if model != "gpt-4o":
            model = "gpt-4-vision-preview"
        i = [{"type": "image_url", "image_url": {"url": u}} for u in i]
        content.extend(i)
        config["images"] = None

    A = Sonata.chat_assistant
    messages = A.send_request(config["channel_id"], "user", content).data

    reply = ""
    # append all messages until role is user
    for message in messages:
        if message.role == "user":
            break
        content = message.content
        for c in content:
            reply += "\n" + c.text.value if c.type == "text" else f":{c.source.url}:"

    return reply


@MANAGER.register_ai(
    None,
    key=settings.X_AI,
    setup=lambda S, key: setattr(
        S, "client", openai.OpenAI(api_key=key, base_url="https://api.x.ai/v1")
    ),
    model="grok-beta",
)
def Grok(client, prompt, model, config):
    content = [{"content": prompt, "role": "user"}]

    if config["instructions"]:
        content.insert(
            0,
            {
                "role": "system",
                "content": config["instructions"],
            },
        )

    return (
        client.chat.completions.create(
            # client.beta.prompt_caching.messages.create(
            model=model,
            # system=config["instructions"],
            # system=instructions,
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
            messages=content,
        )
        .choices[0]
        .message.content
    )


@MANAGER.register_ai(
    client=openai.chat.completions,
    key=settings.OPEN_AI,
    setup=lambda _, key: setattr(openai, "api_key", key),
    model="gpt-4.1-2025-04-14",
)
def OpenAI(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    images = config.get("images", False)

    if images:
        # if model != "gpt-4o":
        #     model = "gpt-4-vision-preview"
        images = [{"type": "image_url", "image_url": {"url": url}} for url in images]
        content.extend(images)
        config["images"] = None

    return (
        client.create(
            model=model,
            messages=[
                {"role": "system", "content": config["instructions"]},
                {"role": "user", "content": content},
            ],
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
        )
        .choices[0]
        .message.content
    )


@MANAGER.register_ai(
    None,
    key=settings.ANTHROPIC_AI,
    setup=lambda S, key: setattr(S, "client", anthropic.Anthropic(api_key=key)),
    # model="claude-sonnet-4-5-20250929",
    model="claude-haiku-4-5",
)
def Claude(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    i = config.get("images", False)
    instructions = (
        [
            {
                "type": "text",
                "text": config["instructions"],
                # "cache_control": {"type": "ephemeral"},
            }
        ]
        if config.get("instructions", None)
        else [{"type": "text", "text": "Follow all instructions."}]
    )
    old_content = content

    if i:
        images = []
        for u in i:
            response = requests.get(u)
            data = response.content
            content_type = response.headers["content-type"]
            if content_type == "text/plain;charset=UTF-8":
                content_type = "image/gif"
            cprint(f"Image content type: {content_type}", "green")
            b64 = base64.b64encode(data).decode("utf-8")
            images.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": content_type,
                        "data": b64,
                    },
                }
            )

        content = []
        content.extend(old_content)
        content.extend(images)
        config["images"] = None
        Sonata.memory["config"]["images"] = None

    try:
        return (
            client.messages.create(
                # client.beta.prompt_caching.messages.create(
                model=model,
                # system=config["instructions"],
                system=instructions,
                max_tokens=config.get("max_tokens", 1250),
                temperature=config.get("temp") or config.get("temperature") or 0,
                messages=[{"role": "user", "content": content}],
            )
            .content[0]
            .text
        )
    except:
        cprint("Retrying without images...", "yellow")
        return (
            client.messages.create(
                # client.beta.prompt_caching.messages.create(
                model=model,
                # system=config["instructions"],
                system=instructions,
                max_tokens=config.get("max_tokens", 1250),
                temperature=config.get("temp") or config.get("temperature") or 0,
                messages=[{"role": "user", "content": old_content}],
            )
            .content[0]
            .text
        )


@MANAGER.register_ai(
    None,
    default=True,
    key=settings.PPLX_AI,
    setup=lambda S, key: setattr(
        S,
        "client",
        openai.OpenAI(
            api_key=key, base_url="https://api.perplexity.ai"
        ).chat.completions,
    ),
    model="sonar",
)
def Perplexity(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    return (
        client.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
        )
        .choices[0]
        .message.content
    )


@MANAGER.register_ai(
    genai.GenerativeModel,
    default=True,
    key=settings.GOOGLE_AI,
    setup=lambda _, key: genai.configure(api_key=key),
    # model="gemini-2.0-flash-exp",
    # model="gemini-2.5-pro-exp-03-25",
    model="gemini-2.5-flash",
    # model = "gemini-2.5-pro"
)
def Gemini(client, prompt, model, config):
    # Safety settings to unblock all content
    block = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE",
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE",
        },
    ]
    content = prompt
    images = config.get("images", False)
    if images:
        # model = "gemini-1.5-flash"
        images = [Image.open(BytesIO(requests.get(u).content)) for u in images]
        content = [content]
        content.extend(images)
        config["images"] = None
    try:
        response = None
        if type(content) == list:
            content = [config["instructions"]] + content
        else:
            content = config["instructions"] + content
        response = client(
            model_name=model,
            generation_config={
                "temperature": config.get("temp") or config.get("temperature", 0.4)
            },
            safety_settings=block,
        ).generate_content(content)
        return response.text
    except Exception as e:
        if hasattr(response, "prompt_feedback"):
            cprint(response.prompt_feedback, "red")
        else:
            cprint(str(e), "red")
        if (
            str(e) == "429 Resource has been exhausted (e.g. check quota)."
            and model == "gemini-1.5-pro-latest"
        ):
            return (
                client(
                    model_name=model,
                    generation_config={
                        "temperature": config.get("temp")
                        or config.get("temperature", 0.4)
                    },
                    safety_settings=block,
                )
                .generate_content(content)
                .text
            )
        else:
            raise AI_Error(str(e))


# -------------------------------------------------------------------
# Discord Bot Setup
# -------------------------------------------------------------------

extend(Sonata)

# HACK: This is a hack to DESTROY SONATAS MEMORY
if PROMPT_RESET:
    reset_instructions()


class SonataClient(commands.Bot):
    current_guild = ""
    current_channel = ""

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def on_ready(self) -> None:
        cprint("Logged on as {0}!".format(self.user), "purple")
        self.loop.create_task(Sonata.get("termcmd", "hook")(Sonata, self))

    async def on_message(self: commands.Bot, message: discord.Message) -> None:
        if message.guild is None:
            await Sonata.get("chat", "dm_hook")(Sonata, self, message)
        else:
            await Sonata.get("chat", "hook")(Sonata, self, message)


INTENTS = discord.Intents.all()
sonata = SonataClient(command_prefix="$", intents=INTENTS)


# TODO: Move all speaking related things to a separate module
# https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645198
#
speaking_mutex = asyncio.Lock()

# TODO: Connect self-commands to voice chat and filter commands that cant be used
# https://github.com/users/blaqat/projects/1/views/1?pane=issue&itemId=65645210
voice_instructions = """
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

PROMPT_MANAGER.add_prompts(("VoiceInstructions", voice_instructions))


# TODO: Add configuration for voice chat
# - Voice type, live or started by name, etc
# https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645198
async def say(vc: discord.VoiceClient, message, opts={}):
    """While in vc send TTS Audio to play"""
    try:
        audio_bytes: bytes = (
            openai.audio.speech.create(  # Returns The audio file content. HttpxBinaryResponseContent
                model="tts-1",
                # alloy, echo, fable, onyx, nova, shimmer
                voice=opts.get("voice", "sage"),
                input=message,
                response_format="opus",
            ).read()
        )
    except Exception as e:
        cprint(f"Error on openai: {e}", "red")
        return

    buffer = BytesIO(audio_bytes)

    cprint(f"Playing audio: {message}", "green")
    vc.play(discord.FFmpegOpusAudio(buffer, pipe=True))
    while vc.is_playing():
        await asyncio.sleep(1)


async def vc_callback(sink: discord.sinks, channel: discord.TextChannel, *args):
    """
    Callback function to process recorded audio from a voice channel.
    """
    global is_ready
    is_ready = False
    recorded_users = [  # A list of recorded users
        await channel.guild.fetch_member(int(user_id))
        for user_id, _ in sink.audio_data.items()
    ]

    # recorded_users = [await channel.guild.fetch_member(383851442341019658)]
    # sink_data = sink.audio_data.get(383851442341019658, None)
    # if sink_data is None:
    #     return
    # data: BytesIO = sink_data.file

    def get_name(user):
        try:
            if "nick" in dir(user) and user.nick is not None:
                return user.nick
            if "name" in dir(user):
                return user.name
        except AttributeError as _:
            return None

    try:
        for user in recorded_users:
            name = get_name(user)
            if name is None:
                continue
            sink_data = sink.audio_data.get(user.id, None)
            if sink_data is None:
                continue
            data: BytesIO = sink_data.file
            data.seek(1)
            data.name = "audio.mp3"

            # if audio is too short, skip
            if len(data.read()) <= 60000:
                continue

            cprint(f"Transcribing audio from {name}...", "blue")

            words = openai.audio.transcriptions.create(
                file=data,
                model="whisper-1",
                prompt="Your name is Sonata",
            ).text.lower()

            id = sink.vc.channel.id

            #  def send( kelf, id, message_type, author, message, replying_to=None,):
            Sonata.chat.send(id, "User", name, words)

            command = None
            if "sonata" in words:
                command = words
            # if "sona" in words or "?" in words:
            #     command = words

            if command:
                cprint(f"{name}: {words}", "cyan")
                r = Sonata.chat.request(
                    id,
                    command,
                    name,
                    AI="OpenAI",
                    # AI=Sonata.config.get("AI", "Gemini"),
                    instructions=PROMPT_MANAGER.get("VoiceInstructions"),
                    # model="gpt-4o",
                )
                # if response starts with 'sonata' remove it
                if r.strip().startswith("sonata"):
                    r = r.split("sonata")[1].strip()
                r = name + ": " + r
                # Wait for speaking mutex to be released
                await speaking_mutex.acquire()
                await say(sink.vc, r)
                speaking_mutex.release()

    except Exception as e:
        is_ready = True
        cprint(e, "red")

    await start_recording(sink.vc, channel)


async def start_recording(vc, channel):
    try:
        print("Starting recording")
        while not vc.is_connected():
            await asyncio.sleep(1)
        vc.start_recording(discord.sinks.MP3Sink(), vc_callback, channel)
        await asyncio.sleep(8)
        print("Stopping recording")
        vc.stop_recording()
    except Exception as e:
        print(f"Error: {e}")


@sonata.event
async def on_voice_state_update(member, before, after):
    """
    Event handler for voice state updates, specifically for monitoring when the bot joins,
    """
    if member.id == sonata.user.id:
        if before.channel is None and after.channel is not None:
            print(f"Sonata has joined the voice channel: {after.channel.name}")
            # Start recording audio
            vc = member.guild.voice_client
            if VC_RECORDING:
                await start_recording(vc, after.channel)
            else:
                cprint("VC Recording is disabled", "red")
        elif before.channel is not None and after.channel is None:
            print(f"Sonata has left the voice channel: {before.channel.name}")
        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            # Bot moved to another voice channel
            print(
                f"Sonata has moved from {before.channel.name} to {after.channel.name}"
            )
            vc = member.guild.voice_client
            if VC_RECORDING:
                await start_recording(vc, after.channel)
            else:
                cprint("VC Recording is disabled", "red")


CURRENT_VC = None

# -------------------------------------------------------------------
# Bot Commands
# -------------------------------------------------------------------


@sonata.command()
async def respond(ctx):
    """
    Responds in the voice channel based on the chat log and context.
    """
    response_instructions = """
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

    global CURRENT_VC

    if ctx.guild.voice_client is not None:
        CURRENT_VC = ctx.guild.voice_client

    if CURRENT_VC is None:
        voice = ctx.author.voice

        if voice is None:
            await ctx.send("You are not in a voice channel.")

        # Check if the bot is already in a voice channel
        try:
            vc = await voice.channel.connect()
        except:
            server = ctx.message.guild.voice_client
            if server:
                await server.disconnect()
            vc = await voice.channel.connect()

        CURRENT_VC = vc
    else:
        vc = CURRENT_VC

    id = ctx.id
    r = Sonata.chat.request(
        id,
        "Respond to the context based on the chat log",
        "System",
        None,
        AI="OpenAI",
        # AI=Sonata.config.get("AI", "Gemini"),
        instructions=response_instructions,
    )

    await speaking_mutex.acquire()
    await say(vc, r)
    speaking_mutex.release()


@sonata.command()
async def voice(ctx, *voice):
    """
    Changes the voice used for TTS in voice channels.
    """
    if not VC_SPEAKING:
        return await ctx.send("soz voice speaking is disabled")
    VALID_OPTIONS = [
        "alloy",
        "ash",
        "coral",
        "echo",
        "fable",
        "onyx",
        "sage",
        "nova",
        "shimmer",
    ]
    voice = " ".join(voice).lower()

    if voice == "":
        await ctx.send(
            f"Current voice is `{Sonata.config.get('vc_voice', 'nova')}`. Valid options are: `{', '.join(VALID_OPTIONS)}`"
        )
        return

    if voice not in VALID_OPTIONS:
        await ctx.send(
            f"Invalid voice option. Valid options are: {', '.join(VALID_OPTIONS)}"
        )
        return

    Sonata.config.set(vc_voice=voice)
    await ctx.send(f"Voice changed to {voice}")


@sonata.command()
async def talk(ctx, *message):
    """
    Joins the user's voice channel (if not already connected) and speaks the provided message using TTS.
    """
    global CURRENT_VC
    if not VC_SPEAKING:
        return await ctx.send("soz voice speaking is disabled")

    if ctx.guild.voice_client is not None:
        CURRENT_VC = ctx.guild.voice_client

    if CURRENT_VC is None:
        voice = ctx.author.voice

        if voice is None:
            await ctx.send("You are not in a voice channel.")

        # Check if the bot is already in a voice channel
        try:
            vc = await voice.channel.connect()
        except:
            server = ctx.message.guild.voice_client
            if server:
                await server.disconnect()
            vc = await voice.channel.connect()

        CURRENT_VC = vc
    else:
        vc = CURRENT_VC

    m = " ".join(message)

    if m != "":
        await say(vc, m, {"voice": Sonata.config.get("vc_voice", "nova")})


@sonata.command()
async def join(ctx):
    """
    Joins the user's voice channel.
    """
    voice = ctx.author.voice

    if voice is None:
        await ctx.reply("You are not in a voice channel.")

    try:
        await voice.channel.connect()
    except:
        server = ctx.message.guild.voice_client
        await server.disconnect()
        await voice.channel.connect()


@sonata.command()
async def leave(ctx):
    """
    Leaves the current voice channel.
    """
    await ctx.message.guild.voice_client.disconnect()


async def ctx_reply(ctx, r, reply=True):
    """
    Replies to the context, handling both message and interaction contexts.
    """
    try:
        _ = ctx.author
        if reply:
            await ctx.reply(r[:2000], mention_author=False)
        else:
            await ctx.send(r[:2000])
    except AttributeError as _:
        cprint(r[:2000], "red")
        await ctx.send(r[:2000])


async def get_channel(ctx):
    """
    Returns the channel from the context, handling both message and interaction contexts.
    """
    try:
        _ = ctx.author
        return ctx.channel
    except AttributeError as _:
        cprint("Interaction context detected", "yellow")
        cprint(f"Channel: {ctx.channel}", "yellow")
        cprint(f"Id: {ctx.id}", "yellow")
        return ctx
    except Exception as e:
        cprint(f"Error getting channel: {e}", "red")
        raise e


# TODO: Refactor emoji archiving to a separate util file


def get_emoji_id(emoji_str):
    """
    Extracts the emoji ID, animation status, and name from a Discord emoji string.
    """
    animated = "a:" in emoji_str
    name = re.search(r":\w*:", emoji_str)
    if name:
        name = name.group()[1:-1]
    match = re.search(r":\d*>", emoji_str)
    if match:
        return match.group()[1:-1], animated, name
    return None, False, None


def get_emoji_link_from_id(emoji_id, animated=False, name=""):
    """
    Constructs a direct link to a Discord emoji given its ID, animation status, and name.
    """
    if emoji_id is None:
        return
    link = f"https://cdn.discordapp.com/emojis/{emoji_id}"
    if animated:
        ext = ".gif"
    else:
        ext = ".png"
    link += ext
    return link, name, ext


def trans_emo(emoji):
    """
    Transforms a Discord emoji string into a direct link, filename, and extension.
    """
    return get_emoji_link_from_id(*get_emoji_id(emoji))


def download_emoji(direct_link, filename, ext):
    """
    Downloads an emoji from a direct link and saves it to the 'images/' directory.
    """
    directory = "images/"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(directory + filename + ext, "wb") as f:
        f.write(requests.get(direct_link).content)


def chunk_list(lst, chunk_size):
    """
    Splits a list into chunks of a specified size.
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def read_images():
    """
    Reads all images from the 'images/' directory and formats them as emoji codes.
    """
    directory = "images/"
    if not os.path.exists(directory):
        os.makedirs(directory)
    files = os.listdir(directory)
    image_list = [f":{f[:-4]}:" for f in files]
    # sort by name
    image_list.sort()
    image_str = ""
    for i in chunk_list(image_list, 12):
        image_str += " ".join(i) + "\n"
    return image_str


@sonata.command()
async def archive(ctx, *message):
    """
    Archives emojis from the provided message by downloading them.

    Parameters:
        ctx: The command context (e.g., from a Discord bot framework).
        *message: Variable-length arguments representing parts of the message containing emoji codes.
    """
    message = " ".join(message).replace(" ", "").strip()
    emojis = message.split("<")
    emojis = [trans_emo(e) for e in emojis]
    num = 0
    for emoji in emojis:
        if emoji is None:
            continue
        download_emoji(*emoji)
        num += 1
    await ctx.send(f"Archived {num} emoji{'s' if num > 1 else ''}")


@sonata.command()
async def oute(ctx):
    """
    Outputs all archived emojis in chunks of 2000 characters.
    """
    text = read_images()
    print(text)
    while len(text) > 2000:
        s = text[:2000]
        a = ""
        if s[-1] != ":":
            a = s[s.rfind(":") + 1 :]
            s = s[: s.rfind(":") + 1]
        await ctx.send(s)
        text = a + text[2000:]

    await ctx.send(text)


@sonata.command()
async def ping(ctx):
    await ctx_reply(ctx, "pong")


RESPONSE_FAILURES = dict()
MAX_FAILURES = 3


async def ai_question(ctx, *message, ai, short, error_prompt=None):
    """
    General handler for AI question commands.
    """
    global RESPONSE_FAILURES
    Sonata.config.set(AI=ai)
    intercept_reply = Sonata.get("termcmd", "intercept_hook", default=None)
    channel = await get_channel(ctx)
    try:
        message = " ".join(message)
        if message is None or message == "":
            message = "0"
        respond_or_chat = message[-1] == "1"
        message = message[:-1]
        # respond_or_chat = False

        name = get_full_name(ctx)
        _ref = None
        try:
            if Sonata.config.get("view_replies", False):
                _ref = await get_chain(ctx.message)
        except Exception:
            _ref = None
        async with ctx.typing():
            r = Sonata.chat.request(
                channel.id,
                message,
                name,
                _ref,
                AI=ai,
                error_prompt=error_prompt,
                save=False,
            )
            if intercept_reply is not None:
                r = await intercept_reply(r, Sonata)
                await ctx_reply(ctx, r, not respond_or_chat)
            else:
                await ctx_reply(ctx, r, not respond_or_chat)
            Sonata.chat.send(channel.id, "Bot", Sonata.name, r, _ref)
        RESPONSE_FAILURES[(await get_channel(ctx)).id] = 0
    except Exception as e:
        cprint(e, "red")
        print(get_trace())
        chn = channel.id
        RESPONSE_FAILURES[chn] = RESPONSE_FAILURES.get(chn, 0) + 1
        ord_fails = ordinal(RESPONSE_FAILURES[chn])
        cprint(f"AI response failure {RESPONSE_FAILURES[chn]}/{MAX_FAILURES}", "red")
        if RESPONSE_FAILURES[chn] >= MAX_FAILURES:
            await ctx_reply(
                ctx,
                f"THATS THE ***{ord_fails.upper()}*** TIME <@{settings.GOD}> im restarting >:(",
            )
            cprint("Max AI response failures reached, resetting AI Manager", "red")
            restart()
        await ctx_reply(
            ctx,
            f"""
### <@{settings.GOD}> i messed up ({ord_fails} time) :c

```py
{get_trace()}
```""",
        )
    finally:
        Sonata.config.set(auto=short)


@sonata.command(name="g", description="Ask a question using Google Gemini AI.")
async def google_ai_question(ctx, *message):
    await ai_question(
        ctx,
        *message,
        ai="Gemini",
        short="g",
        error_prompt=lambda r, name: PROMPT_MANAGER.get(
            "ExplainBlockReasoning", r, name
        ),
    )


@sonata.command(name="o", description="Ask a question using OpenAI.")
async def open_ai_question(ctx, *message):
    await ai_question(ctx, *message, ai="OpenAI", short="o")


@sonata.command(name="c", description="Ask a question using Claude")
async def claude_ai_question(ctx, *message):
    await ai_question(
        ctx,
        *message,
        ai="Claude",
        short="c",
        error_prompt=lambda r, name: PROMPT_MANAGER.get(
            "ExplainBlockReasoning", r, name
        ),
    )


@sonata.command(name="x", description="Ask a question using Grok")
async def grok_ai_question(ctx, *message):
    await ai_question(
        ctx,
        *message,
        ai="Grok",
        short="x",
        error_prompt=lambda r, name: PROMPT_MANAGER.get(
            "ExplainBlockReasoning", r, name
        ),
    )


@sonata.command(name="a", description="Ask a question using OpenAI Assistant.")
async def open_ai_assistant_question(ctx, *message):
    await ai_question(ctx, *message, ai="Assistant", short="a")


@sonata.command(name="restart", description="Restart the bot.")
async def restart_bot(ctx):
    """
    Command to restart the bot.
    """
    await ctx_reply(
        ctx,
        "https://i.pinimg.com/originals/e8/ee/77/e8ee77cd01795709f86edf724c390ed6.gif",
        reply=True,
    )
    restart()


async def main():
    # TODO: Make other run modes like "flash", "view", "absorb"
    # to handle different pre/post memory scenerios
    if RANDOM_CONFIG:
        rand_config()
    cprint("Initlializing...", "yellow")
    Sonata.beacon.branch("chat").flash()
    cprint("Chat memory flashed", "yellow")
    Sonata.reload("chat", "value", module=True)
    cprint("Chat memory restored", "yellow")
    cprint(
        f"Using Model: {AUTO_MODEL}\nMemory Reset: {PROMPT_RESET}\nGIF Search: {GIF_SEARCH}\nInjecting Emojis: {EMOJIS}",
        "purple",
    )
    await sonata.start(settings.BOT_TOKEN)


def restart():
    cprint("Restarting...", "yellow")
    Sonata.save("chat", "value", module=True)
    Sonata.do("termcmd", "save")
    os.execv(sys.executable, ["python"] + sys.argv)


Sonata.restart = restart


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(get_trace())
    finally:
        cprint("Exiting...", "red")
        Sonata.save("chat", "value", module=True)
        # cprint(f"\nMemory on crash: {Sonata.get('chat')}", "yellow")
        Sonata.do("termcmd", "save")
