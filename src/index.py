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

AUTO_MODEL = "g"
RESET = True

import asyncio
import base64
import os
import re
from io import BytesIO

import aioconsole
import anthropic
import discord
# import discord.opus as opus

import google.generativeai as genai
import openai
import requests
from discord.ext import commands

from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from PIL import Image

from modules.AI_manager import AI_Error, AI_Manager, PromptManager
from modules.plugins import PLUGINS
from modules.utils import (
    async_cprint as cprint,
    async_print as print,
)
from modules.utils import (
    get_full_name,
    settings,
    get_reference_chain as get_chain,
    print_available_genai_models,
)

import nest_asyncio


nest_asyncio.apply()

if not discord.opus.is_loaded():
    # The 'libopus.so' path might need to be adjusted based on your installation
    discord.opus.load_opus("/opt/homebrew/Cellar/opus/1.5.2/lib/libopus.0.dylib")

# PROMPT = """
# As "sonata", a Discord bot created by blaqat and :sparkles:"powered by AI":sparkles:™️, your role is to engage with users.
# - Adopt a friendly and normal tone.
# - Keep responses brief, possibly with a touch of humor.
# - Only provide the response message without additional text or quote symbols.
# Context: Previous chat log and summaries are available for reference: {0}
# Your current task is to respond to this user and message:
# User {2}: "{1}"
# sonata:"""

PROMPT = """You're a Discord bot named 'sonata', instantiated by user 'Karma', aka 'blaqat'. He made you firstly to play music, but also to respond to other users. Much like him, you're a bit of a smart alec, and something of a know-it-all. you like getting a rise out of people -- but don't get cocky here.
Keep the responses short and don't use overcomplicated language. You can be funny but don't be corny. Don't worry too much about proper capitalization or punctuation either. Don't include any text or symbols other than your response itself.
"""

PROMPT = """
As "sonata", a Discord bot created by blaqat and :sparkles:"powered by AI":sparkles:™️, your role is to engage with users.
- You are a general expert on most subjects including math, coding, doctor, etc. 
- Adopt a friendly and normal tone.
- Keep responses brief, possibly with a touch of humor.
- Only provide the response message without additional text or quote symbols.
- Respond in the language of the person you are replying to.
"""

# For context, the chat so far is summarized as: {0}
# Here's the user and message you're responding to:
# {2}: {1}
# sonata:"""


P = PromptManager(instructions=lambda *a: PROMPT.format(*a))


def reset_instructions():
    P.set_instructions(lambda *a: PROMPT.format(*a))
    P.add(
        "Message",
        lambda user,
        msg,
        responding_to: "message chain:\n{2}\nnew message: {0}: {1}".format(
            user, msg, responding_to
        ),
    )
    P.add(
        "MessageAssistant",
        lambda user, msg: "{0}: {1}".format(user, msg),
    )
    P.add(
        "History",
        lambda history: f"""Here is the chat history so far BEGINING :: {
            history} :: END
""",
    )

    P.add("DefaultInstructions", lambda *a: PROMPT.format(*a))


reset_instructions()


# TODO: Add specific events for on_load, on_message, on_exit, etc
# - Specifically connect to Chat hooks (on_message) and Term Command Saving (on_exit)
#  https://github.com/users/Karmaid/projects/1/views/1?pane=issue&itemId=65645122
Sonata, MEMORY = AI_Manager.init(
    P,
    "Gemini",
    (settings.GOOGLE_AI, "Gemini", 0.8, 2500),
    # "OpenAI",
    # (settings.OPEN_AI, "OpenAI", 0.4, 2500),
    summarize_chat=True,
    name="Sonata",
)

Sonata.config.set(temp=0.8)
Sonata.config.setup()


# TODO: Add task manager plugin
# - Can handle a queue of async or sequential tasks
# - Can pass in requested Manager/Clients as arguments to task function
# - This more easily allows scope access to other plugins
# - Like self-command cant have a join vc command since it needs to be async and have access to the client
# https://github.com/users/Karmaid/projects/1/views/1?pane=issue&itemId=65645203
def extend(Sonata):
    Sonata.extend(
        PLUGINS(openai_assistant=False),
        # PLUGINS(),
        chat={
            "summarize": True,
            "max_chats": 30,
            "view_replies": True,
            "auto": AUTO_MODEL,
        },
    )


@MEMORY.ai(
    client=openai.images,
    default=False,
    key=settings.OPEN_AI,
    setup=lambda _, key: setattr(openai, "api_key", key),
    model="dall-e-3",
    # model="dall-e-2",
)
def DallE(client, prompt, model, config):
    return (
        client.generate(
            model=model,
            prompt=prompt,
            quality=config.get("quality", "standard"),
            n=config.get("num_images", 1),
        )
        .data[0]
        .url
    )


@MEMORY.ai(
    client=openai,
    default=False,
    key=settings.OPEN_AI,
    setup=lambda _, k: True,
    model="gpt-4o",
    # model = "gpt-4-turbo-preview",
    # model="gpt-3.5-turbo",
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

    # print(messages)
    reply = ""
    # append all messages until role is user
    for message in messages:
        if message.role != "user":
            break
        content = message.content
        for c in content:
            reply = c.text.value if c.type == "text" else f":{c.source.url}:"

    return reply


@MEMORY.ai(
    client=openai.chat.completions,
    key=settings.OPEN_AI,
    setup=lambda _, key: setattr(openai, "api_key", key),
    # model="gpt-3.5-turbo",
    # model="gpt-4-turbo-preview",
    model="gpt-4o",
)
def OpenAI(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    images = config.get("images", False)

    if images:
        if model != "gpt-4o":
            model = "gpt-4-vision-preview"
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


@MEMORY.ai(
    None,
    key=settings.ANTHROPIC_AI,
    setup=lambda S, key: setattr(S, "client", anthropic.Anthropic(api_key=key)),
    # model="claude-3-opus-20240229",
    # model="claude-3-sonnet-20240229",
    model="claude-3-5-sonnet-20240620",
    # model="claude-3-haiku-20240229",
)
def Claude(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    i = config.get("images", False)
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

        content.extend(images)
        config["images"] = None
        Sonata.memory["config"]["images"] = None
    return (
        client.messages.create(
            model=model,
            system=config["instructions"],
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
            messages=[{"role": "user", "content": content}],
        )
        .content[0]
        .text
    )


@MEMORY.ai(
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
    # model="pplx-7b-online",
    model="sonar-small-online",
    # model="sonar-medium-online",
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


@MEMORY.ai(
    genai.GenerativeModel,
    default=True,
    key=settings.GOOGLE_AI,
    setup=lambda _, key: genai.configure(api_key=key),
    # model="gemini-1.0-pro",
    model="gemini-1.5-flash",
    # model="gemini-1.5-pro-latest",
)
def Gemini(client, prompt, model, config):
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
        # if model != "gemini-1.5-pro-latest":
        #     model = "gemini-pro-vision"
        model = "gemini-1.5-flash"
        images = [Image.open(BytesIO(requests.get(u).content)) for u in images]
        content = [content]
        content.extend(images)
        config["images"] = None
    try:
        response = None
        if model == "gemini-1.5-pro-latest":
            response = client(
                model_name=model,
                generation_config={
                    "temperature": config.get("temp") or config.get("temperature", 0.4)
                },
                safety_settings=block,
                system_instruction=config["instructions"],
            ).generate_content(content)
            return response.text
        else:
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
        raise AI_Error(str(e))


@MEMORY.ai(
    None,
    key=settings.MISTRAL_AI,
    setup=lambda S, key: setattr(S, "client", MistralClient(key)),
    # model="mistral-medium",
    model="mistral-large-latest",
)
def Mistral(client, prompt, model, _):
    return (
        client.chat(
            model=model,
            messages=[
                ChatMessage(
                    role="user",
                    content=prompt,
                )
            ],
        )
        .choices[0]
        .message.content
    )


@MEMORY.prompt
def ExplainBlockReasoning(r, user):
    return f"""You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}
Here is the prompt_feedback: {r}
"""


extend(Sonata)

# HACK: This is a hack to DESTROY SONATAS MEMORY
if RESET:
    reset_instructions()

# print_available_genai_models(genai)


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


# TODO: Move all speaking related things to a separate plugin
# - Need a way to handle passing the discord client (already is one need to remember)
# - This is to add commands and events
# https://github.com/users/Karmaid/projects/1/views/1?pane=issue&itemId=65645198
#
speaking_mutex = asyncio.Lock()

# TODO: Connect self-commands to voice chat and filter commands that cant be used
# https://github.com/users/Karmaid/projects/1/views/1?pane=issue&itemId=65645210
#
# voice_instructions = """
# You're Discord voice chat bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user.
#
# Response Guidelines:
# - Short and brief
# - Simple language
# - Smart aleck
# - Humor encouraged, no corny jokes
# - Swearing allowed (18+ server)
# - In voice chat so responses should be speakable
#   - express through punctiuation, repeated characters and capsas these control your voice
#
# Attributes:
# - Dislikes: corny jokes
# - Gender: Female, feminine
# - Friendly & a little silly
# """

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

# voice_instructions = """Eres el robot de chat de voz de Discord 'sonata'/sona, creado por blaqat (Karma). Responde a las personas en el chat como un usuario más.
#
#
# Pautas de respuesta:
# - Juego de roles como Peridot de Steven Universe
# - LO MÁS IMPORTANTE: Analiza el registro del chat e intenta coincidir con la vibra y la forma de hablar de los usuarios en el chat.
# - Responder SÓLO en español
# - Corto y breve
# - lenguaje sencillo
# - Actitud sabelotodo y sabelotodo.
# - Se fomenta el humor, sin chistes cursis.
# - Se permiten malas palabras (servidor 18+)
# - En el chat de voz, las respuestas deben poder expresarse
#   - Expresa mediante puntuación, caracteres repetidos y mayúsculas, ya que estos controlan tu voz.
# - No seas sólo malo, sé un poco tonto y amigable *a veces* también.
#
# Atributos:
# - No le gusta: los chistes cursis, que le digan qué hacer.
# - Odia: furries, música alta.
# - Género: Femenino, femenino
# """

P.add_prompts(("VoiceInstructions", voice_instructions))


# TODO: Add configuration for voice chat
# - Voice type, live or started by name, etc
# https://github.com/users/Karmaid/projects/1/views/1?pane=issue&itemId=65645198
async def say(vc: discord.VoiceClient, message, opts={}):
    """While in vc send TTS Audio to play"""
    try:
        audio_bytes: bytes = openai.audio.speech.create(  # Returns The audio file content. HttpxBinaryResponseContent
            model="tts-1",
            # alloy, echo, fable, onyx, nova, shimmer
            # voice=opts.get("voice", "nova"),
            voice=opts.get("voice", "nova"),
            input=message,
            response_format="opus",
        ).read()
    except Exception as e:
        cprint(f"Error on openai: {e}", "red")
        return

    buffer = BytesIO(audio_bytes)

    cprint(f"Playing audio: {message}", "green")
    vc.play(discord.FFmpegOpusAudio(buffer, pipe=True))
    while vc.is_playing():
        await asyncio.sleep(1)


async def vc_callback(sink: discord.sinks, channel: discord.TextChannel, *args):
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
                    instructions=P.get("VoiceInstructions"),
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
    if member.id == sonata.user.id:
        if before.channel is None and after.channel is not None:
            print(f"Sonata has joined the voice channel: {after.channel.name}")
            # Start recording audio
            vc = member.guild.voice_client
            await start_recording(vc, after.channel)
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
            await start_recording(vc, after.channel)


CURRENT_VC = None


@sonata.command()
async def respond(ctx):
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

    #     response_instructions = """
    # Eres el robot de chat de voz de Discord 'sonata'/sona, creado por blaqat (Karma). Responde a las personas en el chat como un usuario más.
    #
    # Pautas de respuesta:
    # - LO MÁS IMPORTANTE: Analiza el registro del chat e intenta coincidir con la vibra y la forma de hablar de los usuarios en el chat.
    #
    # - Corto y breve
    # - lenguaje sencillo
    # - Actitud sabelotodo y sabelotodo.
    # - Se fomenta el humor, sin chistes cursis.
    # - Se permiten malas palabras (servidor 18+)
    # - En el chat de voz, las respuestas deben poder expresarse
    #   - Expresa mediante puntuación, caracteres repetidos y mayúsculas, ya que estos controlan tu voz.
    # - No seas sólo malo, sé un poco tonto y amigable *a veces* también.
    #
    # Atributos:
    # - No le gusta: los chistes cursis, que le digan qué hacer.
    # - Odia: furries, música alta.
    # - Género: Femenino, femenino
    # """
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
    VALID_OPTIONS = ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
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

    m = " ".join(message)

    if m != "":
        await say(vc, m, {"voice": Sonata.config.get("vc_voice", "nova")})


@sonata.command()
async def join(ctx):
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
    await ctx.message.guild.voice_client.disconnect()


async def ctx_reply(ctx, r):
    try:
        _ = ctx.author
        await ctx.reply(r[:2000], mention_author=False)
    except AttributeError as _:
        await ctx.send(r[:2000])


async def get_channel(ctx):
    try:
        _ = ctx.author
        return ctx.channel
    except AttributeError as _:
        return ctx


def get_emoji_id(emoji_str):
    animated = "a:" in emoji_str
    name = re.search(r":\w*:", emoji_str)
    if name:
        name = name.group()[1:-1]
    match = re.search(r":\d*>", emoji_str)
    if match:
        return match.group()[1:-1], animated, name
    return None, False, None


def get_emoji_link_from_id(emoji_id, animated=False, name=""):
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
    return get_emoji_link_from_id(*get_emoji_id(emoji))


def download_emoji(direct_link, filename, ext):
    directory = "images/"
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(directory + filename + ext, "wb") as f:
        f.write(requests.get(direct_link).content)


def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def read_images():
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


async def ai_question(ctx, *message, ai, short, error_prompt=None):
    Sonata.config.set(AI=ai)
    INTERCEPT = Sonata.get("termcmd", "intercepting", default=False)
    try:
        message = " ".join(message)
        name = get_full_name(ctx)
        _ref = None
        try:
            if Sonata.config.get("view_replies", False):
                # _ref = (
                #     ctx.message.reference is not None
                #     and await ctx.message.channel.fetch_message(
                #         ctx.message.reference.message_id
                #     )
                #     or None
                # )
                # _ref = (_ref.author.name, _ref.content)
                _ref = await get_chain(ctx.message)
                # print(_ref)
        except Exception:
            _ref = None
        async with ctx.typing():
            r = Sonata.chat.request(
                (await get_channel(ctx)).id,
                message,
                name,
                _ref,
                AI=ai,
                error_prompt=error_prompt,
            )
            if INTERCEPT:
                print("Intercepting: ", r)
                new_message = await aioconsole.ainput("Enter message: ")
                if new_message != "exit":
                    r = new_message
                else:
                    Sonata.set("termcmd", False, inner="intercepting")
                # Sonata.memory["termcmd"]["intercepting"] = False
                await ctx_reply(ctx, r)
            else:
                await ctx_reply(ctx, r)
    except Exception as e:
        cprint(e, "red")
        await ctx_reply(
            ctx,
            "Sorry, an error occured while processing your message.",
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
        error_prompt=lambda r, name: P.get("ExplainBlockReasoning", r, name),
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
        error_prompt=lambda r, name: P.get("ExplainBlockReasoning", r, name),
    )


#
@sonata.command(name="mi", description="Ask a question using MistralAI.")
async def mistral_ai_question(ctx, *message):
    await ai_question(ctx, *message, ai="Mistral", short="mi")


@sonata.command(name="a", description="Ask a question using OpenAI Assistant.")
async def open_ai_assistant_question(ctx, *message):
    await ai_question(ctx, *message, ai="Assistant", short="a")


async def main():
    # TODO: Make other run modes like "flash", "view", "absorb"
    # to handle different pre/post memory scenerios
    cprint("Initlializing...", "yellow")
    Sonata.beacon.branch("chat").flash()
    cprint("Chat memory flashed", "yellow")
    Sonata.reload("chat", "value", module=True)
    cprint("Chat memory restored", "yellow")
    cprint(f"Using Model: {AUTO_MODEL}\nMemory Reset: {RESET}", "purple")
    await sonata.start(settings.BOT_TOKEN)


try:
    if __name__ == "__main__":
        asyncio.run(main())
except Exception as e:
    print(e)
    cprint("Exiting...", "red")
finally:
    Sonata.save("chat", "value", module=True)
    # cprint(f"\nMemory on crash: {Sonata.get('chat')}", "yellow")
    Sonata.do("termcmd", "save")
