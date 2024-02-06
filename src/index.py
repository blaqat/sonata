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

from modules.utils import cprint, check_inside, settings, get_full_name
from modules.AI_manager import PromptManager, AI_Manager, AI_Type, AI_Error
import discord
from discord.ext import commands
import openai
import google.generativeai as genai
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from modules.plugins import PLUGINS_ORD as PLUGINS

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

Sonata.extend(PLUGINS, chat={"summarize": True, "max_chats": 35})

print(Sonata.get("chat", "default_value"))

Sonata.config.set(temp=0.8)
Sonata.config.setup()


@M.ai(
    client=openai.ChatCompletion,
    default=True,
    setup=lambda _, key: setattr(openai, "api_key", key),
    model="gpt-3.5-turbo-1106",
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


class SonataClient(commands.Bot):
    current_guild = ""
    current_channel = ""

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def on_ready(self) -> None:
        print("Logged on as {0}!".format(self.user))

    async def on_message(self: commands.Bot, message: discord.Message) -> None:
        await Sonata.get("chat", "hook")(Sonata, self, message)


INTENTS = discord.Intents.all()
sonata = SonataClient(command_prefix="$", intents=INTENTS)


# TODO: Delete all current functions and restructure for a more scalable bot
@sonata.command()
async def ping(ctx):
    await ctx.send("pong")


@sonata.command(name="g", description="Ask a question using Google Gemini AI.")
async def google_ai_question(ctx, *message):
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        # SonataManager.chat.send(ctx.channel.id, "User", name, message)
        r = Sonata.chat.request(
            ctx.channel.id,
            message,
            name,
            AI="Gemini",
            error_prompt=lambda r: P.get("ExplainBlockReasoning", r, name),
        )
        await ctx.send(r[:2000])
    except Exception as e:
        cprint(e, "red")
        await ctx.send("Sorry, an error occured while processing your message.")


@sonata.command(name="o", description="Ask a question using OpenAI.")
async def open_ai_question(ctx, *message):
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        # SonataManager.chat.send(ctx.channel.id, "User", name, message)
        r = Sonata.chat.request(ctx.channel.id, message, name, AI="OpenAI")
        await ctx.send(r[:2000])
    except Exception as e:
        cprint(e, "red")
        await ctx.send("Sorry, an error occured while processing your message.")


@sonata.command(name="mi", description="Ask a question using MistralAI.")
async def mistral_ai_question(ctx, *message):
    try:
        message = " ".join(message)
        name = get_full_name(ctx.author)
        # SonataManager.chat.send(ctx.channel.id, "User", name, message)
        r = Sonata.chat.request(ctx.channel.id, message, name, AI="Mistral")
        await ctx.send(r[:2000])
    except Exception as e:
        cprint(e, "red")
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
        Sonata.chat.delete()
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
    Sonata.chat.delete()
    await ctx.send("Memory cleared.")


@sonata.command(name="memory", description="Sets the bot's memory")
async def set_memory(ctx, *message):
    if not is_god(ctx.author.id):
        await ctx.send(
            "You cannot use this command, you are not a god. Use $god to check if you are a god."
        )
        return
    Sonata.chat.send(ctx.channel.id, "System", "OldMemory", " ".join(message))
    await ctx.send("Memory set.")


def is_god(user_id):
    return Sonata.do("GOD", "verify", str(user_id))


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


sonata.run(token=settings.BOT_TOKEN)

cprint(f"\nMemory on crash: {Sonata.get('chat')}", "yellow")
