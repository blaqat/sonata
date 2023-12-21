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

from modules.utils import *
from modules.AI_manager import *
import discord
from discord.ext import commands
import pretty_errors
import google.generativeai as genai

PROMPT = """
As "sonata", a Discord bot created by blaqat and :sparkles:"powered by AI":sparkles:™️, your role is to engage with users. 
- Adopt a friendly and normal tone.
- Keep responses brief, possibly with a touch of humor.
- Only provide the response message without additional text or quote symbols.
Context: Previous chat log and summaries are available for reference: {0}
Your current task is to respond to this user and message:
User {2}: "{1}"

sonata:
"""

default_prompt = "" + PROMPT
cmds = ["send_message(message)", "laugh(all_caps: bool)", "nothing()"]


# PROMPT = """You're Discord bot 'sonata', instantiated by user 'karma', aka 'numa' or 'Aiden.' He made you firstly to play music, but also to respond to other users. Much like him, you're a little smug, and something of a know-it-all. you like getting a rise out of people -- but don't get cocky here.
#         Keep the responses short and don't use overcomplicated language. You can be funny but don't be corny. Don't worry too much about proper capitalization or punctuation either. Don't include any text or symbols other than your response itself.
#         For context, the chat so far is summarized as: {0}
#         Here's the user and message you're responding to:
#         {2}: "{1}"

#         sonata:"""

o = PromptManager(prompt_name="ChatInstructions",
                  prompt_text=lambda *a: PROMPT.format(*a))

o.add("SummarizeChat",
      lambda chat_log: f"""CHAT LOG SUMMARY: Summarize the chat log in as little tokens as possible. 
- Mention people by name or nickname.
- Maintain chronological order.
- Start response with 'CHAT LOG SUMMARY'
Chat Log: {chat_log}"
""")

genai.configure(api_key=settings.GOOGLE_AI)
g = genai.GenerativeModel('gemini-pro', generation_config={"temperature": .4})
# o.config(key=settings.OPEN_AI, model='gpt-4-1106-preview')
o.config(key=settings.OPEN_AI, model='gpt-3.5-turbo-1106', temperature=.4)


MEMORY = []
COUNT = 0
MAX_COUNT = 50
BANNED_SUB_WORDS = {'cunt', 'cock', 'balls', 'aggin', 'reggin', 'nigger', 'rape', 'tit', 'tiddies', 'penis', 'boob', 'puss', 'nig', 'kys', 'retard', 'sex',
                    'porn', 'kill yourself', 'kill your self', 'black people', "dick", "blow in from", "fuck me", "fuck you", "pussy", "kill themself", "kiya self", "shut the fuck up", "stfu", "stupid", "suck my", "suck me", "bitch"}
CHANNEL_BLACK_LIST = {1175907292072398858, }
GODS = {settings.GOD, '150398769651777538',
        '148471246680621057', '334039742205132800', '272770172434120705'}


class Sonata(commands.Bot):
    current_guild = ''
    current_channel = ''

    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)

    async def on_ready(self) -> None:
        print('Logged on as {0}!'.format(self.user))

    async def on_message(self: commands.Bot, message: discord.Message) -> None:
        global MOST_RECENT_USER
        global COUNT
        _guild_name = message.guild.name
        _channel_name = message.channel.name
        _name = message.author.nick if 'nick' in dir(
            message.author) else message.author.name
        if _name and _name == 'None' or not _name:
            _name = message.author.name

        if message.channel.id in CHANNEL_BLACK_LIST:
            return

        if _guild_name != self.current_guild:
            cprint("\n" + _guild_name.lower(), 'purple', '_')
            self.current_guild = _guild_name

        if _channel_name != self.current_channel:
            cprint("#" + _channel_name, 'green', end=" ")
            print(f"({message.channel.id})")
            self.current_channel = _channel_name

        message.content = censor_bad_words(message.content)

        print("  {0}: {1}".format(cstr(str=_name, style='cyan'), message.content.replace('\n', '\n\t')
                                  ))

        if len(MEMORY) > MAX_COUNT:
            print("SUMMARIZING MEMORY")
            log = "\n".join(MEMORY)
            r = o.send("SummarizeChat", f'Chat Log:\n{log}')
            print("SUMMARY TEST", r['response'])
            MEMORY.clear()
            MEMORY.append(r['response'])
            COUNT = 0

        memory_text = message.author.name + \
            (f' (Nickname {_name})' if _name != message.author.name else '')

        memory_text = memory_text.strip()

        if check_inside(BANNED_SUB_WORDS, message.content.lower()):
            if "$" == message.content[0]:
                memory_text += ": #" * len(message.content)
                message.content = "$not-allowed"
                await self.process_commands(message)
        else:
            memory_text += f": {message.content}"
            await self.process_commands(message)

        # if
        MEMORY.append(
            memory_text)
        COUNT += 1


INTENTS = discord.Intents.all()
sonata = Sonata(command_prefix='$', intents=INTENTS)


@sonata.command()
async def ping(ctx):
    await ctx.send('pong')


@sonata.command(name="g", description="Ask a question using Google Gemini AI.")
async def google_ai_question(ctx, *message):
    try:
        m = ' '.join(message)
        fm = o.get('ChatInstructions', MEMORY, m, ctx.author.nick)
        r = g.generate_content(fm)
        await ctx.send(r.text[:2000])
    except Exception as e:
        print(r.prompt_feedback, e)
        reason = r.prompt_feedback.block_reason
        r = g.generate_content(
            "Given is the reason you blocked the previous message. Respond explaining why you blocked it. \nReason: {0}".format(reason))
        await ctx.send(r.text[:2000])


@sonata.command(name="o", description="Ask a question using OpenAI.")
async def open_ai_question(ctx, *message):
    if not is_god(ctx.author.id):
        await ctx.send("You cannot use this command, you are not a god. Use $g instead.")
        return
    m = ' '.join(message)
    r = o.send(
        "ChatInstructions", MEMORY, m, ctx.author.nick)
    r, c = check_if_has_command(r['response'])
    await ctx.send(r[:2000])
    if c:
        await run_command(ctx, c[0], *c[1])


@sonata.command(name="not-allowed", description="I'm not allowed to respond to that.")
async def not_allowed(ctx):
    await ctx.send("I'm not allowed to respond to that.")


@sonata.command(name="cpr", description="Changes the bot's prompt. And resets the memory")
async def change_prompt_m(ctx, *message):
    global COUNT, PROMPT
    if not is_god(ctx.author.id):
        await ctx.send("You cannot use this command, you are not a god. Use $god to check if you are a god.")
        return
    new_prompt = ' '.join(message)
    if not check_inside({"{0}", "{1}", "{2}"}, new_prompt):
        await ctx.send("New prompt must contain:```\n{0} - ChatLog\n{1} - UserMessage\n{2} - UserName")
    else:
        PROMPT = new_prompt
        MEMORY.clear()
        COUNT = 0
        await ctx.send("Prompt changed. Resetting memory.")


@sonata.command(name="cp", description="Changes the bot's prompt.")
async def change_prompt(ctx, *message):
    global PROMPT
    if not is_god(ctx.author.id):
        await ctx.send("You cannot use this command, you are not a god. Use $god to check if you are a god.")
        return
    new_prompt = ' '.join(message)
    if not check_inside({"{0}", "{1}", "{2}"}, new_prompt):
        await ctx.send("New prompt must contain:```\n{0} - ChatLog\n{1} - UserMessage\n{2} - UserName")
    else:
        PROMPT = new_prompt
        await ctx.send("Prompt changed.")


@sonata.command(name="reset", description="Resets the bot's memory.")
async def reset(ctx):
    global COUNT, PROMPT
    if not is_god(ctx.author.id):
        await ctx.send("You cannot use this command, you are not a god. Use $god to check if you are a god.")
        return
    PROMPT = default_prompt
    MEMORY.clear()
    COUNT = 0
    await ctx.send("Memory cleared.")


@sonata.command(name="memory", description="Sets the bot's memory")
async def set_memory(ctx, *message):
    global MEMORY
    if not is_god(ctx.author.id):
        await ctx.send("You cannot use this command, you are not a god. Use $god to check if you are a god.")
        return
    MEMORY = ["MEMORY: " + ' '.join(message)]
    await ctx.send("Memory set.")


def is_god(user_id):
    return str(user_id) in GODS


@sonata.command(name="god", description="Checks if you are a god.")
async def god(ctx):
    if is_god(ctx.author.id):
        await ctx.send("Yes, you are a god.")
    else:
        await ctx.send("No, you are not a god.")


def check_if_has_command(message):
    lines = message.split('\n')
    lines.reverse()
    c = None
    for line in lines:
        if line and line[0] == '$':
            command = line[1:].split('(')[0]
            args = line.split('(')[1].split(')')[0].split('|')
            c = [command, args]
            break
    if c:
        message = message.replace(
            '$' + c[0] + '(' + '|'.join(c[1]) + ')', '').strip()
    return message, c


async def run_command(ctx, command, *args):
    print("RUNNING", command, args)
    match command:
        case "send_message":
            await ctx.send(' '.join(args))
        case "laugh":
            print("LAUGHING")
            await ctx.send("HAHAHHAHAA")
        case _:
            print("NO COMMAND FOUND", command)


def censor_bad_words(message):
    for word in BANNED_SUB_WORDS:
        message = message.lower().replace(word, "#" * len(word))
    return message


sonata.run(token=settings.BOT_TOKEN)
