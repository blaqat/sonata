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

from modules.utils import cprint, check_inside, cstr, settings, find_matches, inside
from modules.AI_manager import PromptManager, ai, AIManager, AI_Type, AIError
import re
import discord
from discord.ext import commands
import google.generativeai as genai
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage

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
{2}: "{1}"
sonata:"""


@ai(
    genai.GenerativeModel,
    setup=lambda _, key: genai.configure(api_key=key),
    model="gemini-pro",
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
        raise AIError(r.prompt_feedback)


@ai(
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


P = PromptManager(prompt_name="Instructions", prompt_text=lambda *a: PROMPT.format(*a))


P.add(
    "SummarizeChat",
    lambda chat_log: f"""CHAT LOG SUMMARY: Summarize the chat log in as little tokens as possible.
- Mention people by name or nickname.
- Maintain chronological order.
- Start response with 'CHAT LOG SUMMARY'
Chat Log: {chat_log}"
""",
)

P.add(
    "ExplainBlockReasoning",
    lambda r, user: f"""
You blocked the previous message. I will give you the prompt_feedback for the previous message.
Explain why you blocked the previous message in a brief conversational tone to the user {user}
Here is the prompt_feedback: {r}
""",
)

P.add("DefaultInstructions", lambda *a: PROMPT.format(*a))
SonataManager = AIManager(
    P,
    "OpenAI",
    (settings.OPEN_AI, "gpt-3.5-turbo-1106", 0.4, 2500),
    summarize_chat=False,
    name="sonata",
)

AI_Type.initalize(
    ("OpenAI", settings.OPEN_AI),
    ("Gemini", settings.GOOGLE_AI),
    ("Mistral", settings.MISTRAL_AI),
)

SonataManager.chat.max_chats = 35
SonataManager.remember(
    "chat",
    {
        "cunt",
        "fuck",
        "nigger",
        "rape",
        "kys",
        "kill your",
        "faggot",
    },
    inner="banned_words",
)

SonataManager.effect(
    "chat",
    "set",
    lambda _, chat_id, message_type, author, message: (
        chat_id,
        message_type,
        author,
        censor_message(message),
    ),
)

CHANNEL_BLACK_LIST = {1175907292072398858, 724158738138660894, 725170957206945859}
SonataManager.remember(
    "chat",
    {1175907292072398858, 724158738138660894, 725170957206945859},
    inner="blacklist",
)

SonataManager.remember(
    "GOD",
    [
        settings.GOD,
        "150398769651777538",
        "148471246680621057",
        "334039742205132800",
        "497844474043432961",
        "143866772360134656",
    ],
)
SonataManager.add("GOD", "update", lambda M, check: check in M["value"])
SonataManager.add("GOD", "set", lambda M, new: M["value"].append(new))
SonataManager.add("GOD", "remove", lambda M, remove: M["value"].remove(remove))


class Sonata(commands.Bot):
    current_guild = ""
    current_channel = ""

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def on_ready(self) -> None:
        print("Logged on as {0}!".format(self.user))

    async def on_message(self: commands.Bot, message: discord.Message) -> None:
        global COUNT
        _guild_name = message.guild.name
        _channel_name = message.channel.name
        _name = (
            message.author.nick
            if "nick" in dir(message.author)
            else message.author.name
        )
        if _name and _name == "None" or not _name:
            _name = message.author.name

        if message.channel.id in CHANNEL_BLACK_LIST:
            return

        if _guild_name != self.current_guild:
            cprint("\n" + _guild_name.lower(), "purple", "_")
            self.current_guild = _guild_name

        if _channel_name != self.current_channel:
            cprint("#" + _channel_name, "green", end=" ")
            print(f"({message.channel.id})")
            self.current_channel = _channel_name

        print(
            "  {0}: {1}".format(
                cstr(str=_name, style="cyan"),
                censor_message(message.content.replace("\n", "\n\t")),
            )
        )

        memory_text = message.author.name + (
            f" (Nickname {_name})" if _name != message.author.name else ""
        )

        memory_text = memory_text.strip()
        if message.content[0] != "$":
            SonataManager.chat.send(
                message.channel.id,
                "User",
                get_full_name(message.author),
                message.content,
            )

        memory_text += f": {message.content}"
        # TODO: Add a self-command system for bot to recursively call functions on itself
        if message.content[0] == "$" and message.author.name == "sonata":
            cprint("COMMAND " + message.content, "cyan")
        await self.process_commands(message)


INTENTS = discord.Intents.all()
sonata = Sonata(command_prefix="$", intents=INTENTS)


# TODO: Delete all current functions and restructure for a more scalable bot
@sonata.command()
async def ping(ctx):
    await ctx.send("pong")


def get_full_name(author):
    name = author.name
    if "nick" in dir(author) and author.nick is not None:
        name += f" (Nickname: {author.nick})"
    return name


@sonata.command(name="g", description="Ask a question using Google Gemini AI.")
async def google_ai_question(ctx, *message):
    print("GOOGLE AI QUESTION")
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        SonataManager.chat.send(ctx.channel.id, "User", name, message)
        r = SonataManager.chat.request(
            ctx.channel.id,
            message,
            name,
            AI="Gemini",
            error_prompt=lambda r: P.get("ExplainBlockReasoning", r, name),
        )
        await ctx.send(r[:2000])
    except Exception as e:
        cprint(e, "red")
        cprint(r, "yellow")
        await ctx.send("Sorry, an error occured while processing your message.")


@sonata.command(name="o", description="Ask a question using OpenAI.")
async def open_ai_question(ctx, *message):
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        SonataManager.chat.send(ctx.channel.id, "User", name, message)
        r = SonataManager.chat.request(ctx.channel.id, message, name, AI="OpenAI")
        await ctx.send(r[:2000])
    except Exception as e:
        cprint(e, "red")
        cprint(r, "yellow")
        await ctx.send("Sorry, an error occured while processing your message.")


@sonata.command(name="mi", description="Ask a question using MistralAI.")
async def mistral_ai_question(ctx, *message):
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        SonataManager.chat.send(ctx.channel.id, "User", name, message)
        r = SonataManager.chat.request(ctx.channel.id, message, name, AI="Mistral")
        await ctx.send(r[:2000])
    except Exception as e:
        cprint(e, "red")
        cprint(r, "yellow")
        await ctx.send("Sorry, an error occured while processing your message.")


@sonata.command(name="not-allowed", description="I'm not allowed to respond to that.")
async def not_allowed(ctx):
    await ctx.send("I'm not allowed to respond to that.")


@sonata.command(
    name="cpr", description="Changes the bot's prompt. And resets the memory"
)
async def change_prompt_m(ctx, *message):
    global PROMPT
    if not is_god(ctx.author.id):
        await ctx.send(
            "You cannot use this command, you are not a god. Use $god to check if you are a god."
        )
        return
    new_prompt = " ".join(message)
    if not check_inside({"{0}", "{1}", "{2}"}, new_prompt):
        await ctx.send(
            "New prompt must contain:```\n{0} - ChatLog\n{1} - UserMessage\n{2} - UserName"
        )
    else:
        PROMPT = new_prompt
        SonataManager.chat.delete()
        await ctx.send("Prompt changed. Resetting memory.")


@sonata.command(name="cp", description="Changes the bot's prompt.")
async def change_prompt(ctx, *message):
    global PROMPT
    if not is_god(ctx.author.id):
        await ctx.send(
            "You cannot use this command, you are not a god. Use $god to check if you are a god."
        )
        return
    new_prompt = " ".join(message)
    if not check_inside({"{0}", "{1}", "{2}"}, new_prompt):
        await ctx.send(
            "New prompt must contain:```\n{0} - ChatLog\n{1} - UserMessage\n{2} - UserName"
        )
    else:
        PROMPT = new_prompt
        await ctx.send("Prompt changed.")


@sonata.command(name="reset", description="Resets the bot's memory.")
async def reset(ctx):
    global PROMPT
    if not is_god(ctx.author.id):
        await ctx.send(
            "You cannot use this command, you are not a god. Use $god to check if you are a god."
        )
        return
    SonataManager.chat.delete()
    await ctx.send("Memory cleared.")


@sonata.command(name="memory", description="Sets the bot's memory")
async def set_memory(ctx, *message):
    if not is_god(ctx.author.id):
        await ctx.send(
            "You cannot use this command, you are not a god. Use $god to check if you are a god."
        )
        return
    SonataManager.chat.send(ctx.channel.id, "System", "OldMemory", " ".join(message))
    await ctx.send("Memory set.")


def is_god(user_id):
    return SonataManager.do("GOD", "verify", str(user_id))


@sonata.command(name="god", description="Checks if you are a god.")
async def god(ctx):
    if is_god(ctx.author.id):
        await ctx.send("Yes, you are a god.")
    else:
        await ctx.send("No, you are not a god.")


def check_if_has_command(message):
    lines = message.split("\n")
    lines.reverse()
    c = None
    for line in lines:
        if line and line[0] == "$":
            command = line[1:].split("(")[0]
            args = line.split("(")[1].split(")")[0].split("|")
            c = [command, args]
            break
    if c:
        message = message.replace("$" + c[0] + "(" + "|".join(c[1]) + ")", "").strip()
    return message, c


def censor_message(message):
    return re.sub(
        "|".join(
            [re.escape(word) for word in SonataManager.get("chat", "banned_words")]
        ),
        lambda m: "#" * len(m.group()),
        message,
        flags=re.IGNORECASE,
    )


async def run_command(ctx, command, *args):
    print("RUNNING", command, args)
    match command:
        case "send_message":
            await ctx.send(" ".join(args))
        case "laugh":
            print("LAUGHING")
            await ctx.send("HAHAHHAHAA")
        case _:
            print("NO COMMAND FOUND", command)


sonata.run(token=settings.BOT_TOKEN)

cprint(f"\nMemory on crash: {SonataManager.get('chat')}", "yellow")
