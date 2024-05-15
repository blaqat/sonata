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

import asyncio
import base64
import os
import re
from io import BytesIO

import aioconsole
import anthropic
import discord
import google.generativeai as genai
import openai
import requests
from discord.ext import commands
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from PIL import Image

from modules.AI_manager import AI_Error, AI_Manager, AI_Type, PromptManager, AI_TYPES
from modules.plugins import PLUGINS as get_plugins
from modules.utils import (
    async_cprint as cprint,
    async_print as print,
)
from modules.utils import (
    get_full_name,
    settings,
    # print_available_genai_models,
)

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
# For context, the chat so far is summarized as: {0}
# Here's the user and message you're responding to:
# {2}: {1}
# sonata:"""


P = PromptManager(instructions=lambda *a: PROMPT.format(*a))
P.add(
    "Message",
    lambda user, msg, responding_to: """[replying to: {2}] {0}: {1}""".format(
        user, msg, responding_to
    ),
)
P.add("DefaultInstructions", lambda *a: PROMPT.format(*a))


# TODO: Add specific events for on_load, on_message, on_exit, etc
# - Specifically connect to Chat hooks (on_message) and Term Command Saving (on_exit)
Sonata, M = AI_Manager.init(
    P,
    "Gemini",
    # "OpenAI",
    (settings.GOOGLE_AI, "Gemini", 0.4, 2500),
    summarize_chat=True,
    name="Sonata",
)

Sonata.config.set(temp=0.8)
Sonata.config.setup()


@M.ai(
    client=openai.images,
    default=False,
    key=settings.OPEN_AI,
    setup=lambda _, key: setattr(openai, "api_key", key),
    # model="dall-e-3",
    model="dall-e-2",
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


@M.ai(
    client=openai,
    default=False,
    key=settings.OPEN_AI,
    setup=lambda _, k: print("starting up assistant"),
    model="gpt-4o",
)
def OpenAIAssistant(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    i = config.get("images", False)
    if i:
        # model = "gpt-4-vision-preview"
        i = [{"type": "image_url", "image_url": {"url": u}} for u in i]
        content.extend(i)
        config["images"] = None

    A = Sonata.chat_assistant
    messages = A.send_request(config["channel_id"], "user", content).data

    # print(messages)
    reply = ""
    # appent all messages until role is user
    for message in messages:
        if message.role == "user":
            break
        content = message.content
        for c in content:
            if c.type == "text":
                reply += c.text.value
            elif c.type == "image":
                reply += f":{c.source.url}:"

    return reply


@M.ai(
    client=openai.chat.completions,
    default=True,
    key=settings.OPEN_AI,
    setup=lambda _, key: setattr(openai, "api_key", key),
    # model="gpt-3.5-turbo-0125",
    # model="gpt-4-turbo-preview",
    model="gpt-4o",
)
def OpenAI(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    i = config.get("images", False)
    if i:
        # model = "gpt-4-vision-preview"
        i = [{"type": "image_url", "image_url": {"url": u}} for u in i]
        content.extend(i)
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


@M.ai(
    None,
    setup=lambda S, key: setattr(S, "client", anthropic.Anthropic(api_key=key)),
    key=settings.ANTHROPIC_AI,
    # model="claude-3-opus-20240229",
    model="claude-3-sonnet-20240229",
    # model="claude-3-haiku-20240229",
)
def Claude(client, prompt, model, config):
    content = [{"type": "text", "text": prompt}]
    i = config.get("images", False)
    if i:
        i = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.b64encode(requests.get(u).content),
                },
            }
            for u in i
        ]
        content.extend(i)
        config["images"] = None
    return (
        client.messages.create(
            model=model,
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
            messages=[{"role": "user", "content": prompt}],
        )
        .content[0]
        .text
    )


@M.ai(
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


@M.ai(
    genai.GenerativeModel,
    key=settings.GOOGLE_AI,
    setup=lambda _, key: genai.configure(api_key=key),
    model="gemini-pro",
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
    i = config.get("images", False)
    if i:
        model = "gemini-pro-vision"
        i = [Image.open(BytesIO(requests.get(u).content)) for u in i]
        content = [content]
        content.extend(i)
        config["images"] = None
    try:
        return (
            client(
                model_name=model,
                generation_config={
                    "temperature": config.get("temp") or config.get("temperature", 0.4)
                },
                safety_settings=block,
            )
            .generate_content(content)
            .text
        )
    except Exception as e:
        raise AI_Error(str(e))


@M.ai(
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


@M.prompt
def ExplainBlockReasoning(r, user):
    return f"""You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}
Here is the prompt_feedback: {r}
"""


Sonata.extend(
    get_plugins(self_commands=False),
    # WARNING: Dont allow self commands until new history/system instructions are implemented
    # get_plugins(),
    chat={
        "summarize": True,
        "max_chats": 25,
        "view_replies": True,
        "auto": "o",
    },
)


class SonataClient(commands.Bot):
    current_guild = ""
    current_channel = ""

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def on_ready(self) -> None:
        print("Logged on as {0}!".format(self.user))
        self.loop.create_task(Sonata.get("termcmd", "hook")(Sonata, self))

    async def on_message(self: commands.Bot, message: discord.Message) -> None:
        if message.guild is None:
            await Sonata.get("chat", "dm_hook")(Sonata, self, message)
        else:
            await Sonata.get("chat", "hook")(Sonata, self, message)


INTENTS = discord.Intents.all()
sonata = SonataClient(command_prefix="$", intents=INTENTS)


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
                _ref = (
                    ctx.message.reference is not None
                    and await ctx.message.channel.fetch_message(
                        ctx.message.reference.message_id
                    )
                    or None
                )
                _ref = (_ref.author.name, _ref.content)
        except Exception as e:
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
                print("Intercepting")
                new_message = await aioconsole.ainput("Enter message: ")
                if new_message != "exit":
                    r = new_message
                INTERCEPT = False
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
    await ai_question(ctx, *message, ai="Claude", short="c")


#
@sonata.command(name="mi", description="Ask a question using MistralAI.")
async def mistral_ai_question(ctx, *message):
    await ai_question(ctx, *message, ai="Mistral", short="mi")


@sonata.command(name="a", description="Ask a question using OpenAI Assistant.")
async def open_ai_assistant_question(ctx, *message):
    await ai_question(ctx, *message, ai="OpenAIAssistant", short="a")


async def main():
    try:
        await sonata.start(settings.BOT_TOKEN)
    except:
        cprint("Exiting...", "red")
    finally:
        # TODO: Store memory on crash and reload it
        cprint(f"\nMemory on crash: {Sonata.get('chat')}", "yellow")
        Sonata.do("termcmd", "save")


if __name__ == "__main__":
    asyncio.run(main())
