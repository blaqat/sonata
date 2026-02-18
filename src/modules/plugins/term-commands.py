"""
Terminal-Commands
-------------
This plugin allows you to interact with the bot through the terminal. You can send messages, delete messages, join voice channels, and more.
Additionally, you can set favorite channels and users to easily interact with them.
"""

from functools import reduce
from typing import Callable
import discord
from pydantic_core.core_schema import WithInfoValidatorFunction
from modules.AI_manager import AI_Manager
from modules.utils import (
    BColor,
    Colors,
    async_cprint as cprint,
    async_print as print,
    get_reference_chain,
    setter,
    cstr,
)
import asyncio
from random import randint
from prompt_toolkit.formatted_text import ANSI

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(
    lazy=True,
    config={
        "inject_emojis": False,
    },
)
__plugin_name__ = "term_commands"
__dependencies__ = ["beacon", "chat"]
from modules.utils import prompt, editable_prompt, E

"""
Hooks    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


async def term_handler(Data_Manager: AI_Manager, client):
    """Main loop for handling terminal commands"""
    print("Type 'help' for a list of commands")
    INJECT_EMOJIS = MANAGER.MANAGER.config.get("inject_emojis", False)

    if INJECT_EMOJIS:
        # Load all archived emojis
        for guild in client.guilds:
            if guild.name.startswith("blaqat"):
                for emoji in guild.emojis:
                    Data_Manager.do("emojis", "add", emoji)

        # HACK: Inject EmojiIndex into the System Instructions
        old_instructions = Data_Manager.prompt_manager.get_instructions()
        emojis_list = Data_Manager.do("emojis", "list")
        # 1 random number minimum 0, max length of emojis_list - 1000
        num_chars = 600

        def reload_emojis():
            cprint("reloading emojis", "red")
            rand = randint(0, max(1, len(emojis_list) - num_chars))

            emoji_instructions = (
                f"You can use the EmojiIndex to send emojis when u feel like it (only when its contextually significant/DONT ABUSE) (Make sure to use its full <x:name:id> as shown in the index):\n"
                + Data_Manager.do("emojis", "list")[rand : rand + num_chars]
            )

            instructions = None

            if type(old_instructions) == str:
                instructions = old_instructions + emoji_instructions
            else:
                instructions = (
                    lambda *args, **kwargs: old_instructions(*args, **kwargs)
                    + emoji_instructions
                )

            Data_Manager.prompt_manager.set_instructions(
                prompt=instructions,
                prompt_name=Data_Manager.prompt_manager.instructions,
            )

        reload_emojis()

    while True:
        if INJECT_EMOJIS and randint(1, 100) > 90:
            reload_emojis()
        # If intercepting, wait
        if Data_Manager.get("termcmd", "intercepting", default=False):
            await asyncio.sleep(1)
            continue
        try:
            user_input = await prompt("❯ ", color="purple")
        except KeyboardInterrupt:
            await client.close()
        except E:
            return
        try:
            await Data_Manager.do("termcmd", "run", user_input, client, Data_Manager)
        except Exception as e:
            cprint(e, "red")


async def intercept_reply(response: str, Data_Manager: AI_Manager) -> str:
    r = response

    if Data_Manager.get("termcmd", "intercepting", default=False) is False:
        return r

    try:
        print("Intercepted message: ", response)
        intercept_type = await prompt(
            "(E)dit message or (R)eplace message? ",
            lambda x: x.lower()[0],
            lambda x: x not in ("e", "r"),
            "Invalid choice",
            color=Colors.YELLOW,
        )
        if intercept_type == "e":
            r = await editable_prompt("Edit message: ", response, color=Colors.YELLOW)
        elif intercept_type == "r":
            r = await prompt("Enter new message: ", color=Colors.CYAN)
    except E:
        cprint("Stopped intercepting messages", Colors.BOLD, Colors.RED)
        Data_Manager.set("termcmd", False, inner="intercepting")
    except Exception as e:
        cprint(e, "red")
    finally:
        return r


@MANAGER.effect("chat", "set", prepend=False)
def save_recent_message(_, chat_id, message_type, author, message, replying_to=None):
    """Save the recent message details to the terminal commands manager"""
    RECENTS = MANAGER.get("termcmd", "recents")

    RECENTS["channel"] = chat_id
    if message_type == "Bot":
        RECENTS["self_msg"] = chat_id
    return (chat_id, message_type, author, message, replying_to)


"""
Helper Functions -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""



# ...existing code...


async def async_return(ret=None):
    """Return a value asynchronously"""
    return ret


def get_channel(M, self, set=False):
    """Get the current channel or prompt to set one"""
    c = self.get_channel(M["recents"]["pinned"] or M["recents"]["channel"])
    if c is None:
        if not set:
            cprint("No channel set", "red")
            raise E
        return lambda r=True: set_channel(M, self, ret=r)

    if set:
        return lambda: async_return(ret=c)
    return c


async def get_messages(c, check=None, limit=10):
    """Get messages from a channel with optional filtering"""
    messages = []
    async for m in c.history(limit=limit):
        if check is None or check(m):
            messages.append(m)
    return messages


def get_emojis(emojis):
    """Convert emoji objects to their string representations"""
    return [
        (
            f"<{e.animated and "a" or ""}:{e.name}:{e.id}>"
            if not isinstance(e, CustomEmoji)
            else f"{e.e}"
        )
        for e in emojis
    ]


def search_emoji(A: AI_Manager, self, name, find_first=10):
    """Search for emojis by name"""
    default_emojis = A.get("emojis", default=[])
    guild_emojis = [emoji for guild in self.guilds for emoji in guild.emojis]
    found_emojis = [e for e in guild_emojis + default_emojis if name in e.name]
    return found_emojis


def get_all_emojis(A, self):
    """Get all emojis from the client and the manager"""
    default_emojis = A.get("emojis")
    emojis = [emoji for guild in self.guilds for emoji in guild.emojis] + default_emojis
    return emojis


async def get_user(M, self, id):
    """Get a user by ID or from favorites"""
    FAV_PPL = M["saved"]["users"]
    if id == "fav":
        print_many(FAV_PPL.items())
        id = await prompt("Enter fav name: ", FAV_PPL.get, exit_msg="Fav not found")
    id = int(id)
    user = self.get_user(id)
    if user is None:
        cprint("User not found", "red")
        raise E
    return user


def print_many(x):
    """Print a list of items with indices"""
    m = "\n".join(f"{i}: {e}" for i, e in enumerate(x))
    cprint(m, "yellow")
    return m


def print_messages(m):
    """Print messages with indices, authors, and content snippets"""
    m = "\n".join(
        "{}: {}\t| {}".format(i, m.author, m.content[:50]) for (i, m) in enumerate(m)
    )
    cprint(m, "yellow")
    return m


async def get_recent_msg(M, self):
    """Get the most recent message sent by the bot"""
    channel_id = M["recents"]["self_msg"]
    c = self.get_channel(channel_id)
    if c is None:
        cprint("No recent message", "red")
        raise E
    m = await get_messages(c, lambda m: m.author == self.user, 1)
    if not m or len(m) == 0:
        cprint("No recent message...", "red")
        raise E
    return m[0]


async def set_channel(M, self=None, ret=True):
    """Prompt the user to set a channel"""
    FAV_CHN = M["saved"]["channels"]
    c = await prompt("Enter channel id: ")
    if c == "fav":
        print_many(FAV_CHN.keys())
        c = await prompt(
            "Enter fav name: ", FAV_CHN.get, lambda x: x is None, "Fav not found"
        )
    M["recents"]["pinned"] = int(c)
    if ret:
        return self.get_channel(int(c))


class CustomEmoji:
    """Class representing a custom emoji"""

    def __init__(self, name, e):
        self.name = name
        self.id = ""
        self.animated = False
        self.e = e

    @classmethod
    def from_dict(cls, d):
        new_d = []
        for k, v in d.items():
            new_d.append(cls(k, v))
        return new_d


@MANAGER.new_helper("term")
def term_command(F, name=None):
    MANAGER.set("termcmd", name or F.__name__, F)


"""
Setup    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

MANAGER.remember(
    "emojis",
    CustomEmoji.from_dict(
        {
            "sparkling_heart": "💖",
            "ok_hand": "👌",
            "thumbsup": "👍",
            "grey_question": "❔",
            "red_circle": "🔴",
            "raised_eyebrow": "🤨",
            "thinking": "🤔",
            "clap": "👏",
            "smile": "😊",
            "laugh": "😂",
        }
    ),
    set_func=lambda M, name, e: (
        setter(M["value"], name, e)
        if isinstance(M["value"], dict)
        else M["value"].append(CustomEmoji(name, e))
    ),
    update_func=lambda M: (
        CustomEmoji.from_dict(M["value"])
        if isinstance(M["value"], dict)
        else M["value"]
    ),
    add=lambda M, emoji: M["value"].append(emoji),
    list_id=lambda M: f"EmojiIndex: {", ".join([str(e.id if e.id else e.e) for e in M["value"]])}",
    list_name=lambda M: f"EmojiIndex: {", ".join([e.name for e in M["value"]])}",
    list=lambda M: f"EmojiIndex: {", ".join(get_emojis(M["value"]))}",
)


# Initalize Emoji Storage
MANAGER.update("emojis")


# Initalize termcmd plugin
@MANAGER.mem(
    {},
    set=lambda M, name, func: setter(M["value"], name, func),
    # save=__save_favs,
    # load=__load_favs,
    save=lambda _: MANAGER.MANAGER.save("termcmd", "saved"),
    load=lambda _: MANAGER.MANAGER.reload("termcmd", "saved"),
    intercepting=False,
    recents={
        "pinned": None,
        "channel": None,
        "server": None,
        "self_msg": None,
        "voice_chat": None,
        "termcmd": None,
    },
    saved={
        "channels": {"test": 876743264139624458},
        "users": {"amy": 754188427699945592},
    },
    hook=term_handler,
    intercept_hook=intercept_reply,
)
def run_termcmd(M, name, client, manager):
    num_required = M["value"][name].__code__.co_argcount
    args = [M, client, manager]
    if M["value"][name] != retry_prev_command:
        M["recents"]["termcmd"] = (name, args[:num_required])
    return run_command(M["value"], name, args[:num_required])


@MANAGER.on_load
def load_termcmd(Sonata):
    """On load, start the terminal command handler"""
    Sonata.do("termcmd", "load")


"""
Commands  -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


async def run_command(commands, command_name, args):
    """Run a command by name with arguments"""
    output = await commands[command_name](*args)
    return output


@MANAGER.term
async def help(*_):
    """Display a list of available commands"""
    print(
        """
        chn: Set channel
        reset: Reset channel
        god: Send message in channel
        dlr: Delete last message
        dlm: Delete message
        dlc: Delete chat memory
        vc: Join voice channel
        leave: Leave voice channel
        react: React to message
        emosend: Send emoji
        emoji: Search for emoji
        favs: Show favs
        favp: Edit fav person
        favc: Edit fav channel
        dm: Send dm
        dmr: Send dm reply
        edit: Edit message
        reply: Reply to message
        int: Intercept messages
        $: Run command
        cmd: Run command
        sum: Summarize current chat
        pchn: Print channel chat history
        exit: Exit"""
    )


@MANAGER.term("chn")
async def set_pinned_channel(mem):
    """Set the current channel"""
    await set_channel(mem, ret=False)


@MANAGER.term
async def reset_pinned_channel(mem):
    """Reset the pinned channel"""
    mem["recents"]["pinned"] = None


@MANAGER.term("god")
async def send_msg(mem, bot):
    """Send a message in the current channel"""
    c = get_channel(mem, bot)
    async with c.typing():
        if c.guild is not None:
            cprint(f"Sending message in {c.name}")
        else:
            cprint(f"Sending message to {c.recipient.name}")
        msg = await prompt("Enter message: ")
        await MANAGER.do("chat", "chat", bot, c.id, msg)


@MANAGER.term("dlr")
async def del_recent_msg(mem, bot):
    """Delete the most recent message sent by the bot"""
    RECENT_SELF_MSG = await get_recent_msg(mem, bot)
    await RECENT_SELF_MSG.delete()


@MANAGER.term("dlm")
async def del_msg(mem, bot):
    """Delete a specific message in the current channel"""
    c = get_channel(mem, bot)
    messages = await get_messages(c, lambda m: m.author == bot.user)
    cprint("Select a message to delete:", "red")
    print_messages(messages)
    i = await prompt(
        "Enter index: ",
        int,
        exit_if=lambda i: i < 0 or i >= len(messages),
        exit_msg="Invalid index",
    )
    await messages[i].delete()


@MANAGER.term("dlc")
async def del_chat_memory(mem, bot):
    """Delete chat memory for the current channel"""
    beacon = MANAGER.MANAGER.beacon.branch("chat").branch("value")
    chat = MANAGER.MANAGER.chat
    current_channel = bot.get_channel(
        mem["recents"]["pinned"] or mem["recents"]["channel"]
    )
    choice = await prompt(
        "Delete (c)urrent chat, (f)avorite chat, (a)ll chats, or (n)new chat:\n",
        str.lower,
    )
    channel = None
    # Determine which chat memory to delete
    if choice[0] == "c":
        if current_channel is None:
            cprint("No current channel", "red")
            raise E
        channel = current_channel.id
    elif choice[0] == "f":
        favs = mem["saved"]["channels"]
        print_many(favs.keys())
        c = await prompt(
            "Enter fav name: ", favs.get, lambda x: x is None, "Fav not found"
        )
        channel = c
    elif choice == "all":
        # scan does return os.listdir(self.home)
        for file in beacon.scan():
            file = file.split(".")[0]
            chat.delete(int(file[1:]))
            beacon.dim(file)
        return
    elif choice[0] == "n":
        channel = await prompt("Enter channel id: ")
    elif choice == "exit":
        return

    # Validate the channel and delete chat memory
    if channel is None:
        cprint("Invalid choice", "red")
        raise E
    else:
        chat.delete(int(channel))  # Deletes live chat memory
        beacon.dim(f"i{channel}")  # Deletes saved chat memory

        delete_backup = await prompt("Delete backups? (y/n): ", lambda x: x[0] == "y")

        if delete_backup:
            beacon.flash(save=False).dim(f"i{channel}")  # Deletes chat memory backup
            cprint(f"Deleted chat {channel} and flashbacks", "yellow")
        else:
            cprint(f"Deleted chat {channel}", "yellow")


@MANAGER.term("vc")
async def join_vc(mem, bot):
    """Join a voice channel"""
    VOICE_CHAT = mem["recents"]["voice_chat"]
    if VOICE_CHAT is not None:
        await VOICE_CHAT.disconnect()
        mem["recents"]["voice_chat"] = None
    chn = get_channel(mem, bot)
    g = chn.guild
    c = None
    if g is None:
        c = await prompt("Enter vc id: ", int)
        c = await bot.fetch_channel(c)
    else:
        channels = [c for c in g.channels if c.type == discord.ChannelType.voice]
        cprint("Select a voice channel:", "yellow")
        print_many(channels)
        i = await prompt(
            "",
            int,
            exit_if=lambda i: i < 0 or i >= len(channels),
            exit_msg="Invalid index",
        )
        c = channels[i]

    try:
        mem["recents"]["voice_chat"] = await c.connect()
    except Exception as e:
        server = g.voice_client
        await server.disconnect()
        mem["recents"]["voice_chat"] = await c.connect()


@MANAGER.term
async def leave(mem):
    """Leave the current voice channel"""
    VOICE_CHAT = mem["recents"]["voice_chat"]
    if VOICE_CHAT is not None:
        await VOICE_CHAT.disconnect()
        mem["recents"]["voice_chat"] = None
    else:
        cprint("Not in a voice channel", "red")
        raise E


@MANAGER.term
async def rejoin(mem, bot):
    """Rejoin the last voice channel"""
    VOICE_CHAT = mem["recents"]["voice_chat"]
    if VOICE_CHAT is not None:
        await VOICE_CHAT.disconnect()
        mem["recents"]["voice_chat"] = None
    chn = await get_channel(mem, bot, set=True)()
    g = chn.guild
    c = None

    # Select a voice channel
    if g is None:
        c = await prompt("Enter vc id: ", int)
        c = await bot.fetch_channel(c)
    else:
        channels = [c for c in g.channels if c.type == discord.ChannelType.voice]
        cprint("Select a voice channel:", "yellow")
        print_many(channels)
        i = await prompt(
            "",
            int,
            exit_if=lambda i: i < 0 or i >= len(channels),
            exit_msg="Invalid index",
        )
        c = channels[i]

    # Join the voice channel
    try:
        vc = await c.connect()
        await vc.disconnect()
        mem["recents"]["voice_chat"] = await c.connect()
    except Exception as e:
        vc = await c.connect()
        await vc.disconnect()
        mem["recents"]["voice_chat"] = await c.connect()


@MANAGER.term
async def ai():
    """Set the AI type for the bot"""
    ai = await prompt(
        "Enter AI name: ",
        exit_if=lambda x: x
        not in ("OpenAI", "Claude", "Mistral", "Assistant", "Gemini", "Perplexity"),
        exit_msg="Invalid AI",
    )

    MANAGER.MANAGER.memory["config"]["AI"] = ai


@MANAGER.term
async def mute(mem, bot):
    """Mute or unmute the bot in the current voice channel"""
    set_mute = prompt("Mute? (y/n): ", lambda x: x[0] == "y", lambda x: x[0] == "n")
    vc = get_channel(mem, bot).guild.voice_client

    if vc and vc.channel:
        await vc.edit_voice_state(mute=set_mute)
    else:
        cprint("Not in a voice channel", "red")
        raise E


@MANAGER.term
async def react(mem, bot, manager):
    """React to a message in the current channel"""
    c = get_channel(mem, bot)
    messages = await get_messages(c)
    print_messages(messages)
    i = await prompt(
        "Enter index: ",
        int,
        lambda i: i < 0 or i >= len(messages),
        exit_msg="Invalid index",
    )
    s = await prompt("Enter emoji name: ")
    emojis = search_emoji(manager, bot, s, 10)
    emojis = get_emojis(emojis)
    cprint(f"Pick an emoji to send:", "yellow")
    print_many(emojis)
    i2 = await prompt(
        "Enter index: ", int, lambda i: i < 0 or i >= len(emojis), "Invalid index"
    )
    await messages[i].add_reaction(emojis[i2])


@MANAGER.term("emote")
async def send_emojis(mem, bot, manager):
    """Send an emoji in the current channel"""
    c = get_channel(mem, bot)
    s = await prompt("Enter emoji name: ")
    emojis = search_emoji(manager, bot, s, 10)
    emojis = get_emojis(emojis)
    cprint(f"Pick an emoji to send:", "yellow")
    print_many(emojis)
    i = await prompt(
        "Enter index: ", int, lambda i: i < 0 or i >= len(emojis), "Invalid index"
    )
    # await c.send(emojis[i])
    await MANAGER.do("chat", "chat", bot, c.id, emojis[i])


@MANAGER.term("emojis")
async def search_emojis(_, bot, manager):
    """Search for emojis by name"""
    s = await prompt("Enter emoji name: ")
    emojis = search_emoji(manager, bot, s, 10)
    emojis = get_emojis(emojis)
    cprint(f"Found {len(emojis)} emojis: {emojis}", "yellow")


@MANAGER.term("favs")
async def print_favs(mem):
    """Display favorite channels and users"""
    FAV_CHN = mem["saved"]["channels"]
    FAV_PPL = mem["saved"]["users"]
    cprint(f"\nChannels: {FAV_CHN}", "yellow")
    cprint(f"Users: {FAV_PPL}", "yellow")


@MANAGER.term("favp")
async def fav_user(mem, bot):
    """Manage favorite users"""
    FAV_PPL = mem["saved"]["users"]
    name = await prompt("Edit or Add")

    # Add a new favorite user
    if name == "a" or name == "add" or name == "":
        pid = await prompt("Enter user id: ", int)
        p = await get_user(mem, bot, pid)
        if p is None:
            cprint("User not found", "red")
            raise E
        name = await prompt(f"Replace name: {p.display_name} ")
        if name == "n" or name == "" or not name:
            name = p.display_name
        FAV_PPL[name] = pid
        cprint(f"Added {name}:{pid} to favs", "yellow")
    # Edit an existing favorite user
    elif name == "e" or name == "edit":
        print_many(FAV_PPL.items())
        name = await prompt(
            "Edit name: ",
            exit_if=lambda x: x not in FAV_PPL,
            exit_msg="Fav not found",
        )
        n = name
        i = FAV_PPL[n]
        name = await prompt(f"Replace name: {n}")
        if name == "n" or name == "" or not name:
            name = n
        pid = await prompt(f"Replace id: {FAV_PPL[n]}")
        if pid == "n" or pid == "" or not pid:
            pid = i
        del FAV_PPL[n]
        FAV_PPL[name] = pid
        cprint(f"Edited {name}:{pid} in favs", "yellow")
    # Delete a favorite user
    elif name == "d" or name == "delete":
        print_many(FAV_PPL.items())
        name = await prompt(
            "Delete fav: ",
            None,
            lambda x: x is None or x not in FAV_PPL,
            "Fav not found",
        )
        del FAV_PPL[name]
        cprint(f"Deleted {name} from favs", "yellow")
        return


@MANAGER.term("favc")
async def fav_channel(mem, bot):
    """Manage favorite channels"""
    FAV_CHN = mem["saved"]["channels"]
    channel = get_channel(mem, bot)
    channels = {f"Current: {channel.name}": channel.id}
    channels.update(FAV_CHN)
    print_many(channels)
    name = await prompt("Add channel to favs: (or new)")

    if name == "c" or name == "current" or name == "0":
        id = channel.id
        name = await prompt(f"Replace name: {channel.name} ")
        if name == "n" or name == "" or not name:
            name = channel.name
        FAV_CHN[name] = id
    elif name == "new" or name == "n":
        id = await prompt("Enter id: ", int)
        c = bot.get_channel(id)
        if c is None:
            cprint("Channel not found", "red")
            raise E
        name = await prompt(f"Replace name:  {c.name} ")
        if name == "n" or name == "" or not name:
            name = c.name
        FAV_CHN[name] = c.id
    elif name == "d" or name == "delete":
        print_many(FAV_CHN.items())
        name = await prompt(
            "Delete fav: ",
            None,
            lambda x: x is None or x not in FAV_CHN,
            "Fav not found",
        )
        del FAV_CHN[name]
        cprint(f"Deleted {name} from favs", "yellow")
        return
    else:
        if name not in FAV_CHN:
            cprint("Fav not found", "red")
            raise E
        id = await prompt(f"Replace id: {FAV_CHN[name]}")
        if id == "n" or id == "" or not id:
            id = FAV_CHN[name]
        new_name = await prompt(f"Replace name: {name}")
        if new_name == "n" or new_name == "" or not new_name:
            name = new_name
        FAV_CHN[name] = id
    cprint(f"Added {name}:{id} to favs", "yellow")


@MANAGER.term
async def dm(mem, bot, manager):
    """Send a direct message to a user"""
    id = await prompt("Enter user id: ")
    user = await get_user(mem, bot, id)
    print(f"Selected User: {user.display_name}")
    msg = await prompt("Enter message: ")
    # await user.send(msg)
    await manager.do("chat", "chat", bot, user.id, msg, dm=True)


@MANAGER.term("dmr")
async def dm_reply(mem, bot, manager):
    """Reply to a direct message from a user"""
    id = await prompt("Enter user id: ")
    user = await get_user(mem, bot, id)
    c = user.dm_channel
    if not c:
        c = await user.create_dm()
    messages = await get_messages(c)
    cprint("Select a message to reply to:", "yellow")
    print_messages(messages)
    i = await prompt("", int, lambda i: i < 0 or i >= len(messages), "Invalid index")
    async with c.typing():
        msg = await prompt("Enter message: ")
        # await messages[i].reply(msg)
        await manager.do(
            "chat", "chat", bot, c.id, msg, dm=True, replying_to=messages[i]
        )


@MANAGER.term
async def edit(mem, bot):
    """Edit a message sent by the bot in the current channel"""
    c = get_channel(mem, bot)
    messages = await get_messages(c, lambda m: m.author == bot.user)
    cprint("Select a message to edit:", "yellow")
    print_messages(messages)
    i = await prompt("", int, lambda i: i < 0 or i >= len(messages), "Invalid index")
    r = await prompt(
        "(R)eplace or (E)dit message: ",
        lambda x: x.lower()[0],
        lambda x: x not in ("r", "e"),
        "Invalid choice",
    )
    if r == "e":
        msg = await editable_prompt("Edit message: ", messages[i].content)
    else:
        msg = await prompt("Enter new message: ")

    await messages[i].edit(content=msg)


@MANAGER.term
async def reply(mem, bot):
    """Reply to a message in the current channel"""
    c = get_channel(mem, bot)
    messages = await get_messages(c, lambda m: m.author != bot.user)
    cprint("Select a message to reply to:", "yellow")
    print_messages(messages)
    i = await prompt("", int, lambda i: i < 0 or i >= len(messages), "Invalid index")
    async with c.typing():
        msg = await prompt("Enter message: ")
        ping = await prompt("Ping author? (y/n): ", str.lower) == "y"
        # await messages[i].reply(msg, mention_author=ping)
        await MANAGER.do(
            "chat", "chat", bot, c.id, msg, dm=True, replying_to=messages[i], ping=ping
        )


@MANAGER.term("int")
async def enable_intercepting(mem):
    """Enable message interception mode"""
    mem["intercepting"] = True
    cprint(f"Intercepting messages: ", "yellow")


@MANAGER.term("$")
async def god_cmd(mem, bot):
    """Run a command in the current channel"""
    c = get_channel(mem, bot)
    command = await prompt("Enter command text: ", lambda x: x.split(" "))
    args = command[1:]
    command = command[0]
    try:
        bot.loop.create_task(bot.get_command(command).callback(c, *args))
    except Exception as _:
        cprint("Command not found", "red")
        raise E


@MANAGER.term("sum")
async def summarize_chat(mem, bot):
    """Summarize the chat history in the current channel"""
    id = get_channel(mem, bot).id

    summary, D = MANAGER.MANAGER.chat.summarize(id)

    if summary is None:
        cprint("No chat to summarize", "red")
        raise E

    await MANAGER.do(
        "chat",
        "chat",
        bot,
        id,
        "## <a:note:1095495413341110302> Chat Summary:\n" + summary,
    )

    delete = await prompt(
        "Do you want to delete the chat after summarizing? (y/n): ",
        lambda a: a[0] == "y",
    )

    if delete:
        D()


@MANAGER.term("pchn")
async def print_channel_history(mem, bot, manager):
    """Print the chat history in the current channel"""
    c = get_channel(mem, bot)
    messages = manager.chat.get_chat(c.id)
    cprint("Channel chat history:", "yellow")
    messages = [f"{m[1]}: {m[2]}" for m in messages]
    print_many(messages)


@MANAGER.term("sc")
async def save_chat():
    """Save the current chat state"""
    MANAGER.MANAGER.chat.save("chat", "value", module=True)


@MANAGER.term("cmd")
async def run_self_cmd(mem, bot, manager):
    """Run a self-command with arguments in the current channel"""
    c = get_channel(mem, bot)
    history = manager.chat.get_history(c.id)
    # ai = client.config.get("AI")
    config = manager.config.copy()
    command = await prompt("Enter self-command: ")
    args = await prompt("Enter args: ")
    config[
        "instructions"
    ] = """ I have just run the {command} command with the following arguments: {args}.
Display the relevant information given from the command output.
"""
    r = manager.prompt_manager.send(
        "SelfCommand",
        history,
        command,
        args,
        AI="Gemini",
        config=config,
    )
    # await c.send(r)
    await MANAGER.do("chat", "chat", bot, c.id, r)


@MANAGER.term
async def respond(mem, bot, manager):
    """Generate a response in the current channel using AI"""

    response_instructions = manager.prompt_manager.get_instructions()

    try:
        channel = bot.get_channel(MANAGER.get("termcmd", "recents")["channel"])
        if channel is None:
            raise E
    except Exception as e:
        cprint(e, "red")
        print("No channel set")
        channel = await get_channel(mem, bot, set=True)()

    AI = manager.config.get("AI")

    r = manager.chat.request(
        channel.id,
        "Awaiting your response...",
        "System",
        None,
        instructions=response_instructions,
        AI=AI,
    )

    await MANAGER.do("chat", "chat", bot, channel.id, r, save=False)


@MANAGER.term("res")
async def ai_reply(mem, bot, manager):
    """Reply to a message in the current channel using AI"""
    # Get Message to Reply To
    AI = manager.config.get("AI")
    chn = get_channel(mem, bot)
    messages = await get_messages(chn, lambda m: m.author != bot.user, limit=20)

    # Select Message
    cprint("Select a message to reply to:", "yellow")
    print_messages(messages)
    i = await prompt("", int, lambda i: i < 0 or i >= len(messages), "Invalid index")
    responding_to = messages[i]

    # Get reply chain
    _ref = None
    try:
        if manager.config.get("view_replies", False):
            _ref = await get_reference_chain(responding_to)
    except Exception:
        _ref = None

    async with chn.typing():
        # Request message until satisfied
        retry = True
        while retry:
            retry = False
            msg = manager.chat.request(
                chn.id,
                responding_to.content,
                responding_to.author.name,
                _ref,
                instructions=manager.prompt_manager.get_instructions(),
                AI=AI,
            )
            cprint(f"Generated response: {msg}", "cyan")

            # Prompt to edit, retry, or send the message
            msg_choice = await prompt(
                "(E)dit, (I)ntercept, (R)etry, or (S)end message? ",
                lambda x: x.lower()[0],
                lambda x: x.lower()[0] not in ("i", "e", "r", "s"),
                "Invalid choice",
            )
            match msg_choice:
                case "e":
                    msg = await editable_prompt("Edit message: ", msg, color="purple")
                case "i":
                    msg = await prompt("Enter new message: ", color="yellow")
                case "r":
                    retry = True

        # Send message
        ping = await prompt("Ping author? (y/n): ", lambda x: x[0].lower() == "y")
        await messages[i].reply(msg, mention_author=ping)


@MANAGER.term("retry")
async def retry_prev_command(mem):
    if mem["recents"]["termcmd"] is None:
        cprint("No recent command to retry", "red")
        raise E

    return await run_command(mem["value"], *mem["recents"]["termcmd"])


@MANAGER.term
async def restart(_, __, manager):
    manager.restart()
