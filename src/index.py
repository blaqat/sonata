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

from posixpath import expandvars
from modules.utils import (
    async_cprint as cprint,
    async_print as print,
    check_inside,
    settings,
    get_full_name,
    print_list as lprint,
)
from modules.AI_manager import PromptManager, AI_Manager, AI_Type, AI_Error
import discord
from discord.ext import commands
import openai
import google.generativeai as genai
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from modules.plugins import *
import asyncio
import aioconsole


# PROMPT = """
# As "sonata", a Discord bot created by blaqat and :sparkles:"powered by AI":sparkles:™️, your role is to engage with users.
# - Adopt a friendly and normal tone.
# - Keep responses brief, possibly with a touch of humor.
# - Only provide the response message without additional text or quote symbols.
# Context: Previous chat log and summaries are available for reference: {0}
# Your current task is to respond to this user and message:
# User {2}: "{1}"
# sonata:"""

PROMPT = """You're Discord bot 'sonata', instantiated by user 'Karma', aka 'blaqat'. He made you firstly to play music, but also to respond to other users. Much like him, you're a bit of a smart alec, and something of a know-it-all. you like getting a rise out of people -- but don't get cocky here.
Keep the responses short and don't use overcomplicated language. You can be funny but don't be corny. Don't worry too much about proper capitalization or punctuation either. Don't include any text or symbols other than your response itself.
For context, the chat so far is summarized as: {0}
Here's the user and message you're responding to:
{2}: {1}
sonata:"""


P = PromptManager(prompt_name="Instructions", prompt_text=lambda *a: PROMPT.format(*a))
P.add("DefaultInstructions", lambda *a: PROMPT.format(*a))

Sonata, M = AI_Manager.init(
    P,
    "OpenAI",
    (settings.OPEN_AI, "gpt-4-turbo-preview", 0.4, 2500),
    summarize_chat=True,
    name="sonata",
)

# TEST: New PLUGINS(extend_list, mode=allow | deny) system
# If no likey, change to always input all plugins in .extend
# and change .extend to support *str extend_list and mode kwarg
Sonata.extend(PLUGINS_LIST, chat={"summarize": True, "max_chats": 25})
print(Sonata.memory["chat"]["set"])
Sonata.config.set(temp=0.8)
Sonata.config.setup()


# ISSUE: Figure out a cheaper solution other than gpt-4 that works well
# TODO: Update openai to newest version. (Will require some rewrite to client)
@M.ai(
    client=openai.ChatCompletion,
    default=True,
    setup=lambda _, key: setattr(openai, "api_key", key),
    # model="gpt-3.5-turbo-0125",
    model="gpt-4-turbo-preview",
)
def OpenAI(client, prompt, model, config):
    return (
        client.create(
            model=model,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
        )
        .choices[0]
        .message.content
    )


@M.ai(
    genai.GenerativeModel,
    setup=lambda _, key: genai.configure(api_key=key),
    model="gemini-pro",
    # model="gemini-1.0-pro-latest",
)
def Gemini(client, prompt, model, config):
    try:
        r = client(
            model,
            generation_config={
                "temperature": config.get("temp") or config.get("temperature", 0.4)
            },
        ).generate_content(prompt)
        return r.text
    except Exception as _:
        raise AI_Error(r.prompt_feedback)


# ISSUE: Mistral AI just sucks, figuure out a better solution or remove it
@M.ai(
    None,
    setup=lambda S, key: setattr(S, "client", MistralClient(key)),
    model="mistral-medium",
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


AI_Type.initalize(
    ("OpenAI", settings.OPEN_AI),
    ("Gemini", settings.GOOGLE_AI),
    ("Mistral", settings.MISTRAL_AI),
)

# for m in genai.list_models():
#     if "generateContent" in m.supported_generation_methods:
#         print(m.name)

RECENT_CHN = None
RECENT_SVR = None
SET_CHN = 876743264139624458
RECENT_SELF_MSG = None
INTERCEPT = False
VOICE_CHAT = None


class SonataClient(commands.Bot):
    current_guild = ""
    current_channel = ""

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def on_ready(self) -> None:
        print("Logged on as {0}!".format(self.user))
        self.loop.create_task(self.handle_input())

    async def get_emojis(self):
        return [emoji for guild in self.guilds for emoji in guild.emojis]

    async def search_emoji(self, name, find_first=10):
        emojis = await self.get_emojis()
        return [e for e in emojis if name in e.name][:find_first]

    async def on_message(self: commands.Bot, message: discord.Message) -> None:
        global RECENT_CHN, RECENT_SELF_MSG, RECENT_SVR
        RECENT_CHN = message.channel.id
        RECENT_SVR = message.guild
        if message.guild is None:
            cprint(f"DM: {message.author.name}: {message.content}", "purple")
        if message.author == self.user:
            RECENT_SELF_MSG = message
        await Sonata.get("chat", "hook")(Sonata, self, message)

    async def handle_input(self):
        global RECENT_CHN, SET_CHN, RECENT_SELF_MSG, INTERCEPT, VOICE_CHAT, RECENT_SVR
        while True:
            if INTERCEPT:
                await asyncio.sleep(1)
                continue
            user_input = await aioconsole.ainput("Enter command: ")
            try:
                match user_input:
                    case "chn":
                        SET_CHN = await aioconsole.ainput("Enter channel id: ")
                        SET_CHN = int(SET_CHN)

                    case "reset":
                        SET_CHN = None

                    case "god":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        if c is None:
                            cprint("No channel set", "red")
                            continue
                        async with c.typing():
                            if c.guild is not None:
                                cprint(f"Sending message in {c.name}")
                            else:
                                cprint(f"Sending message to {c.recipient.name}")
                            msg = await aioconsole.ainput("Enter message: ")
                            if msg == "exit":
                                continue
                            await c.send(msg)

                    case "dlr":
                        if RECENT_SELF_MSG is not None:
                            await RECENT_SELF_MSG.delete()
                        else:
                            c = self.get_channel(SET_CHN or RECENT_CHN)
                            messages = []
                            async for m in c.history(limit=20):
                                if m.author == self.user:
                                    messages.append(m)
                            cprint("Select a message to delete:", "red")
                            m = "\n".join(
                                "{}: {}\t| {}".format(i, m.author, m.content[:50])
                                for (i, m) in enumerate(messages)
                            )
                            cprint(m, "yellow")
                            i = await aioconsole.ainput("Enter index: ")
                            if i == "exit":
                                continue
                            i = int(i)
                            if i < 0 or i >= len(messages):
                                cprint("Invalid index", "red")
                                _ = await aioconsole.ainput("")
                                continue
                            await messages[i].delete()

                    case "dlm":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        messages = []
                        async for m in c.history(limit=20):
                            if m.author == self.user:
                                messages.append(m)
                        cprint("Select a message to delete:", "red")
                        m = "\n".join(
                            "{}: {}\t| {}".format(i, m.author, m.content[:50])
                            for (i, m) in enumerate(messages)
                        )
                        cprint(m, "yellow")
                        i = await aioconsole.ainput("Enter index: ")
                        if i == "exit":
                            continue
                        i = int(i)
                        if i < 0 or i >= len(messages):
                            cprint("Invalid index", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        await messages[i].delete()

                    case "vc":
                        if VOICE_CHAT is not None:
                            await VOICE_CHAT.disconnect()
                            VOICE_CHAT = None
                        g = RECENT_SELF_MSG and RECENT_SELF_MSG.guild or RECENT_SVR
                        c = None
                        if g is None:
                            c = await aioconsole.ainput("Enter vc id: ")
                            c = await self.fetch_channel(int(c))
                            if c == "exit":
                                continue
                        else:
                            channels = [
                                c
                                for c in g.channels
                                if c.type == discord.ChannelType.voice
                            ]
                            cprint("Select a voice channel:", "yellow")
                            m = "\n".join(
                                "{}: {}".format(i, c) for (i, c) in enumerate(channels)
                            )
                            cprint(m, "yellow")
                            i = await aioconsole.ainput("")
                            if i == "exit":
                                continue
                            i = int(i)
                            if i < 0 or i >= len(channels):
                                cprint("Invalid index", "red")
                                _ = await aioconsole.ainput("")
                                continue
                            c = channels[i]

                        VOICE_CHAT = await c.connect()

                    case "leave":
                        if VOICE_CHAT is not None:
                            await VOICE_CHAT.disconnect()
                            VOICE_CHAT = None
                        else:
                            cprint("Not in a voice channel", "red")
                            _ = await aioconsole.ainput("")

                    case "react":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        if c is None:
                            cprint("No channel set", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        messages = [m async for m in c.history(limit=20)]
                        cprint("Select a message to react to:", "yellow")
                        m = "\n".join(
                            "{}: {}".format(i, m.content[:50])
                            for (i, m) in enumerate(messages)
                        )
                        cprint(m, "yellow")
                        i = await aioconsole.ainput("Enter index: ")
                        if i == "exit":
                            continue
                        i = int(i)
                        if i < 0 or i >= len(messages):
                            cprint("Invalid index", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        s = await aioconsole.ainput("Enter emoji name: ")
                        if s == "exit":
                            continue
                        emojis = await self.search_emoji(s, 10)
                        emojis = [
                            f"<{e.animated and "a" or ""}:{e.name}:{e.id}>"
                            for e in emojis
                        ]
                        cprint(f"Pick an emoji to send:", "yellow")
                        m = "\n".join(
                            "{}: {}".format(x, e) for (x, e) in enumerate(emojis)
                        )
                        cprint(m, "yellow")
                        i2 = await aioconsole.ainput("Enter index: ")
                        if i2 == "exit":
                            continue
                        i2 = int(i2)
                        if i2 < 0 or i2 >= len(emojis):
                            cprint("Invalid index", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        # cprint(f"message: {messages[i].content[:100]}", "purple")
                        await messages[i].add_reaction(emojis[i2])

                    case "emosend":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        if c is None:
                            cprint("No channel set", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        s = await aioconsole.ainput("Enter emoji name: ")
                        if s == "exit":
                            continue
                        emojis = await self.search_emoji(s, 10)
                        emojis = [
                            f"<{e.animated and "a" or ""}:{e.name}:{e.id}>"
                            for e in emojis
                        ]
                        cprint(f"Pick an emoji to send:", "yellow")
                        m = "\n".join(
                            "{}: {}".format(i, e) for (i, e) in enumerate(emojis)
                        )
                        cprint(m, "yellow")
                        i = await aioconsole.ainput("Enter index: ")
                        if i == "exit":
                            continue
                        i = int(i)
                        if i < 0 or i >= len(emojis):
                            cprint("Invalid index", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        await c.send(emojis[i])

                    case "emojis":
                        emojis = await self.get_emojis()
                        cprint(f"Found {len(emojis)} emojis: {emojis}", "yellow")

                    case "emoji":
                        s = await aioconsole.ainput("Enter emoji name: ")
                        if s == "exit":
                            continue
                        emojis = await self.search_emoji(s)
                        emojis = [
                            f"<{e.animated and "a" or ""}:{e.name}:{e.id}>"
                            for e in emojis
                        ]
                        cprint(f"Found {len(emojis)} emojis: {emojis}", "yellow")

                    case "dm":
                        id = await aioconsole.ainput("Enter user id: ")
                        if id == "exit":
                            continue
                        id = int(id)
                        user = self.get_user(id)
                        if user is None:
                            cprint("User not found", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        print(f"Selected User: {user.display_name}")
                        msg = await aioconsole.ainput("Enter message: ")
                        if msg == "exit":
                            continue
                        await user.send(msg)

                    case "dmr":
                        id = await aioconsole.ainput("Enter user id: ")
                        if id == "exit":
                            continue
                        id = int(id)
                        user = self.get_user(id)
                        if user is None:
                            cprint("User not found", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        print(f"Selected User: {user.display_name}")
                        c = user.dm_channel
                        if not c:
                            c = await user.create_dm()
                        messages = [m async for m in c.history(limit=20)]
                        cprint("Select a message to reply to:", "yellow")
                        m = "\n".join(
                            "{}: {}\t| {}".format(i, m.author, m.content[:50])
                            for (i, m) in enumerate(messages)
                        )
                        cprint(m, "yellow")
                        i = await aioconsole.ainput("")
                        if i == "exit":
                            continue
                        i = int(i)
                        if i < 0 or i >= len(messages):
                            cprint("Invalid index", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        async with c.typing():
                            msg = await aioconsole.ainput("Enter message: ")
                            if msg == "exit":
                                continue
                            await messages[i].reply(msg)

                    case "reply":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        if c is None:
                            cprint("No channel set", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        messages = []
                        async for m in c.history(limit=20):
                            if m.author != self.user:
                                messages.append(m)
                        cprint("Select a message to reply to:", "yellow")
                        m = "\n".join(
                            "{}: {}\t| {}".format(i, m.author, m.content[:50])
                            for (i, m) in enumerate(messages)
                        )
                        cprint(m, "yellow")
                        i = await aioconsole.ainput("")
                        if i == "exit":
                            continue
                        i = int(i)
                        if i < 0 or i >= len(messages):
                            cprint("Invalid index", "red")
                            _ = await aioconsole.ainput("")
                            continue
                        async with c.typing():
                            msg = await aioconsole.ainput("Enter message: ")
                            if msg == "exit":
                                continue
                            ping = await aioconsole.ainput("Ping author? (y/n): ")
                            if ping == "exit":
                                continue
                            ping = ping.lower() == "y"
                            await messages[i].reply(msg, mention_author=ping)

                    case "int":
                        INTERCEPT = True
                        cprint("Intercepting messages", "yellow")

                    case "cmd":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        if c is None:
                            c = await aioconsole.ainput("Enter channel: ")
                            c = self.get_channel(int(c))
                        if c is None:
                            cprint("No channel set", "red")
                            continue
                        command = await aioconsole.ainput("Enter command text: ")
                        if command == "exit":
                            continue

                        await c.send("God as requested a command")
                        dummy_message = RECENT_SELF_MSG
                        dummy_message.content = command
                        # dummy_message.author.name = "God"
                        # dummy_message.author.bot = False
                        await self.process_commands(dummy_message)

                    case "scmd":
                        c = self.get_channel(SET_CHN or RECENT_CHN)
                        if c is None:
                            c = await aioconsole.ainput("Enter channel: ")
                            c = self.get_channel(int(c))
                        if c is None:
                            cprint("No channel set", "red")
                            continue
                        history = Sonata.chat.get_history(c.id)
                        ai = Sonata.config.get("AI")
                        config = Sonata.get("config")
                        command = await aioconsole.ainput("Enter self-command: ")
                        if command == "exit":
                            continue

                        args = await aioconsole.ainput("Enter args: ")
                        if args == "exit":
                            continue

                        r = Sonata.prompt_manager.send(
                            "SelfCommand",
                            history,
                            command,
                            args,
                            AI=ai,
                            config=config,
                        )

                        await c.send(r)

                    case "exit":
                        break

            except Exception as e:
                cprint(e, "red")

            # print(f"Received: {user_input}")
            # Process the input as needed


INTENTS = discord.Intents.all()
sonata = SonataClient(command_prefix="$", intents=INTENTS)


# TODO: Delete all current and make the actual bot
@sonata.command()
async def ping(ctx):
    await ctx.reply("pong", mention_author=False)


@sonata.command(name="g", description="Ask a question using Google Gemini AI.")
async def google_ai_question(ctx, *message):
    global INTERCEPT
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        _ref = (ctx.author, message)
        async with ctx.typing():
            r = Sonata.chat.request(
                ctx.channel.id,
                message,
                name,
                _ref,
                AI="Gemini",
                error_prompt=lambda r: P.get("ExplainBlockReasoning", r, name),
            )
            if INTERCEPT:
                print("Intercepting")
                new_message = await aioconsole.ainput("Enter message: ")
                if new_message != "exit":
                    r = new_message
                INTERCEPT = False
                await ctx.reply(r[:2000], mention_author=False)
            else:
                await ctx.reply(r[:2000], mention_author=False)
    except Exception as e:
        cprint(e, "red")
        await ctx.reply(
            "Sorry, an error occured while processing your message.",
            mention_author=False,
        )


@sonata.command(name="o", description="Ask a question using OpenAI.")
async def open_ai_question(ctx, *message):
    global INTERCEPT
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        _ref = (ctx.author, message)
        async with ctx.typing():
            r = Sonata.chat.request(ctx.channel.id, message, name, _ref, AI="OpenAI")
            if INTERCEPT:
                new_message = await aioconsole.ainput("Enter message: ")
                if new_message != "exit":
                    r = new_message
                INTERCEPT = False
        await ctx.reply(r[:2000], mention_author=False)
    except Exception as e:
        # cprint(e, "red")
        await ctx.reply(
            "Sorry, an error occured while processing your message.",
            mention_author=False,
        )


#
# @sonata.command(name="mi", description="Ask a question using MistralAI.")
# async def mistral_ai_question(ctx, *message):
#     try:
#         message = " ".join(message)
#         name = get_full_name(ctx.author)
#         r = Sonata.chat.request(ctx.channel.id, message, name, AI="Mistral")
#         await ctx.reply(r[:2000], mention_author=False)
#     except Exception as e:
#         cprint(e, "red")
#         await ctx.reply(
#             "Sorry, an error occured while processing your message.",
#             mention_author=False,
#         )
#
#
# @sonata.command(name="not-allowed", description="I'm not allowed to respond to that.")
# async def not_allowed(ctx):
#     await ctx.reply("I'm not allowed to respond to that.", mention_author=False)
#
#
# @sonata.command(
#     name="cpr", description="Changes the bot's prompt. And resets the memory"
# )
# async def change_prompt_m(ctx, *message):
#     global PROMPT
#     if not is_god(ctx.author.id):
#         await ctx.send(
#             "You cannot use this command, you are not a god. Use $god to check if you are a god."
#         )
#         return
#     new_prompt = " ".join(message)
#     if not check_inside({"{0}", "{1}", "{2}"}, new_prompt):
#         await ctx.send(
#             "New prompt must contain:```\n{0} - ChatLog\n{1} - UserMessage\n{2} - UserName"
#         )
#     else:
#         PROMPT = new_prompt
#         Sonata.chat.delete()
#         await ctx.reply("Prompt changed. Resetting memory.", mention_author=False)
#
#
# @sonata.command(name="cp", description="Changes the bot's prompt.")
# async def change_prompt(ctx, *message):
#     global PROMPT
#     if not is_god(ctx.author.id):
#         await ctx.send(
#             "You cannot use this command, you are not a god. Use $god to check if you are a god."
#         )
#         return
#     new_prompt = " ".join(message)
#     if not check_inside({"{0}", "{1}", "{2}"}, new_prompt):
#         await ctx.send(
#             "New prompt must contain:```\n{0} - ChatLog\n{1} - UserMessage\n{2} - UserName"
#         )
#     else:
#         PROMPT = new_prompt
#         await ctx.reply("Prompt changed.", mention_author=False)
#
#
# @sonata.command(name="reset", description="Resets the bot's memory.")
# async def reset(ctx):
#     global PROMPT
#     if not is_god(ctx.author.id):
#         await ctx.send(
#             "You cannot use this command, you are not a god. Use $god to check if you are a god."
#         )
#         return
#     Sonata.chat.delete()
#     await ctx.reply("Memory cleared.", mention_author=False)
#
#
# @sonata.command(name="memory", description="Sets the bot's memory")
# async def set_memory(ctx, *message):
#     if not is_god(ctx.author.id):
#         await ctx.send(
#             "You cannot use this command, you are not a god. Use $god to check if you are a god."
#         )
#         return
#     Sonata.chat.send(ctx.channel.id, "System", "OldMemory", " ".join(message))
#     await ctx.reply("Memory set.", mention_author=False)
#
#
# def is_god(user_id):
#     return Sonata.do("GOD", "verify", str(user_id))
#
#
# @sonata.command(name="god", description="Checks if you are a god.")
# async def god(ctx):
#     if is_god(ctx.author.id):
#         await ctx.reply("Yes, you are a god.", mention_author=False)
#     else:
#         await ctx.reply("No, you are not a god.", mention_author=False)


# def check_if_has_command(message):
#     lines = message.split("\n")
#     lines.reverse()
#     c = None
#     for line in lines:
#         if line and line[0] == "$":
#             command = line[1:].split("(")[0]
#             args = line.split("(")[1].split(")")[0].split("|")
#             c = [command, args]
#             break
#     if c:
#         message = message.replace("$" + c[0] + "(" + "|".join(c[1]) + ")", "").strip()
#     return message, c


async def main():
    # sonata.loop.sonata.handle_input())
    # sonata.run(token=settings.BOT_TOKEN)
    try:
        await sonata.start(settings.BOT_TOKEN)
    except KeyboardInterrupt:
        cprint("Exiting...", "red")
        # TODO: Store memory on crash and reload it
        cprint(f"\nMemory on crash: {Sonata.get('chat')}", "yellow")


if __name__ == "__main__":
    asyncio.run(main())
    # main()
