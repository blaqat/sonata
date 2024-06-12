"""
Term-Commands
-------------
This plugin allows you to interact with the bot through the terminal. You can send messages, delete messages, join voice channels, and more.
Additionally, you can set favorite channels and users to easily interact with them.
"""

import discord
from discord.utils import sleep_until
from modules.AI_manager import AI_Manager
from modules.utils import (
    async_cprint as cprint,
    async_print as print,
    setter,
    cstr,
)
import os
import asyncio
import aioconsole

L, M, P = AI_Manager.init(lazy=True, config={})
__plugin_name__ = "term_commands"
__dependencies__ = ["beacon", "chat"]


"""
Hooks    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


async def term_handler(A, client):
    print("Type 'help' for a list of commands")
    while True:
        if A.get("termcmd", "intercepting", default=False):
            await asyncio.sleep(1)
            continue
        user_input = await prompt(cstr("❯ ", "purple"))
        try:
            await A.do("termcmd", "run", user_input, client, A)
        except Exception as e:
            cprint(e, "red")


@M.effect("chat", "set", prepend=False)
def save_recent_message(_, chat_id, message_type, author, message, replying_to=None):
    RECENTS = M.get("termcmd", "recents")

    RECENTS["channel"] = chat_id
    if message_type == "Bot":
        RECENTS["self_msg"] = chat_id
    return (chat_id, message_type, author, message, replying_to)


"""
Helper Functions -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


class E(Exception):
    pass


async def prompt(text, convert=None, exit_if=None, exit_msg=None):
    x = await aioconsole.ainput(text)
    if x == "exit":
        raise E
    if convert is not None:
        x = convert(x)
        if x is None:
            cprint(exit_msg or "Invalid conversion", "red")
            raise E
    if exit_if is not None and exit_if(x):
        if exit_msg is not None:
            cprint(exit_msg, "red")
        raise E
    return x


async def async_return(ret=None):
    return ret


def get_channel(M, self, set=False):
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
    messages = []
    async for m in c.history(limit=limit):
        if check is None or check(m):
            messages.append(m)
    return messages


def get_emojis(emojis):
    return [
        f"<{e.animated and "a" or ""}:{e.name}:{e.id}>"
        if not isinstance(e, CustomEmoji)
        else f"{e.e}"
        for e in emojis
    ]


def search_emoji(A, self, name, find_first=10):
    M = A.get("emojis", inner=False)
    M["update"](M)
    emojis = [emoji for guild in self.guilds for emoji in guild.emojis] + M["value"]
    return [e for e in emojis if name in e.name][:find_first]


async def get_user(M, self, id):
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
    m = "\n".join(f"{i}: {e}" for i, e in enumerate(x))
    cprint(m, "yellow")
    return m


def print_messages(m):
    m = "\n".join(
        "{}: {}\t| {}".format(i, m.author, m.content[:50]) for (i, m) in enumerate(m)
    )
    cprint(m, "yellow")
    return m


async def get_recent_msg(M, self):
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


# def __save_favs(TM):
#     with open("trm.favs", "w") as f:
#         f.write(str(TM["saved"]["channels"]) + "\n")
#         f.write(str(TM["saved"]["users"]) + "\n")


# def __load_favs(TM):
#     try:
#         if not os.path.exists("trm.favs"):
#             with open("trm.favs", "w") as f:
#                 f.write(str(TM["saved"]["channels"]) + "\n")
#                 f.write(str(TM["saved"]["users"]) + "\n")
#             return
#         with open("trm.favs", "r") as f:
#             lines = f.readlines()
#             TM["saved"]["channels"] = eval(lines[0])
#             TM["saved"]["users"] = eval(lines[1])
#     except Exception as e:
#         cprint("Error loading favs", "red")
#         cprint(e, "red")


@M.new_helper("term")
def term_command(F, name=None):
    M.set("termcmd", name or F.__name__, F)


"""
Setup    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


M.remember(
    "emojis",
    {
        "sparkling_heart": "💖",
        "ok_hand": "👌",
        "thumbsup": "👍",
        "grey_question": "❔",
        "red_circle": "🔴",
    },
    set_func=lambda M, name, e: setter(M["value"], name, e)
    if isinstance(M["value"], dict)
    else M["value"].append(CustomEmoji(name, e)),
    update_func=lambda M: CustomEmoji.from_dict(M["value"])
    if isinstance(M["value"], dict)
    else M["value"],
)


EMOJIS = M.update("emojis")


@M.mem(
    {},
    set=lambda M, name, func: setter(M["value"], name, func),
    # save=__save_favs,
    # load=__load_favs,
    save=lambda _: M.MANAGER.save("termcmd", "saved"),
    load=lambda _: M.MANAGER.reload("termcmd", "saved"),
    intercepting=False,
    recents={
        "pinned": None,
        "channel": None,
        "server": None,
        "self_msg": None,
        "voice_chat": None,
    },
    saved={
        "channels": {"test": 876743264139624458},
        "users": {"amy": 754188427699945592},
    },
    hook=term_handler,
)
def run_termcmd(M, name, client, manager):
    num_required = M["value"][name].__code__.co_argcount
    args = [M, client, manager]
    # return M["value"][name](*args[:num_required])
    return run_command(M["value"], name, args[:num_required])


@M.on_load
def load_termcmd(M):
    M.do("termcmd", "load")


"""
Commands  -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


async def run_command(V, name, args):
    output = await V[name](*args)
    return output


@M.term
async def help(*_):
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


@M.term
async def chn(M, _):
    await set_channel(M, ret=False)


@M.term
async def reset(M, _):
    M["recents"]["pinned"] = None


@M.term
async def god(m, self):
    c = get_channel(m, self)
    async with c.typing():
        if c.guild is not None:
            cprint(f"Sending message in {c.name}")
        else:
            cprint(f"Sending message to {c.recipient.name}")
        msg = await prompt("Enter message: ")
        await M.do("chat", "chat", self, c.id, msg)


@M.term
async def dlr(M, self):
    RECENT_SELF_MSG = await get_recent_msg(M, self)
    await RECENT_SELF_MSG.delete()


@M.term
async def dlm(M, self):
    c = get_channel(M, self)
    messages = await get_messages(c, lambda m: m.author == self.user)
    cprint("Select a message to delete:", "red")
    print_messages(messages)
    i = await prompt(
        "Enter index: ",
        int,
        exit_if=lambda i: i < 0 or i >= len(messages),
        exit_msg="Invalid index",
    )
    await messages[i].delete()


@M.term
async def dlc(m, self):
    beacon = M.MANAGER.beacon.branch("chat").branch("value")
    chat = M.MANAGER.chat
    current_channel = self.get_channel(
        m["recents"]["pinned"] or m["recents"]["channel"]
    )
    choice = await prompt(
        "Delete (c)urrent chat, (f)avorite chat, (a)ll chats, or (n)new chat:\n",
        str.lower,
    )
    channel = None
    if choice[0] == "c":
        if current_channel is None:
            cprint("No current channel", "red")
            raise E
        channel = current_channel.id
    elif choice[0] == "f":
        favs = m["saved"]["channels"]
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


@M.term
async def vc(M, self):
    VOICE_CHAT = M["recents"]["voice_chat"]
    if VOICE_CHAT is not None:
        await VOICE_CHAT.disconnect()
        M["recents"]["voice_chat"] = None
    chn = get_channel(M, self)
    g = chn.guild
    c = None
    if g is None:
        c = await prompt("Enter vc id: ", int)
        c = await self.fetch_channel(c)
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

    # try:
    #     vc = await voice.channel.connect()
    # except:
    #     server = ctx.message.guild.voice_client
    #     await server.disconnect()
    #     vc = await voice.channel.connect()

    try:
        M["recents"]["voice_chat"] = await c.connect()
    except Exception as e:
        server = g.voice_client
        await server.disconnect()
        M["recents"]["voice_chat"] = await c.connect()


@M.term
async def leave(M, _):
    VOICE_CHAT = M["recents"]["voice_chat"]
    if VOICE_CHAT is not None:
        await VOICE_CHAT.disconnect()
        M["recents"]["voice_chat"] = None
    else:
        cprint("Not in a voice channel", "red")
        raise E


@M.term
async def rejoin(M, self):
    VOICE_CHAT = M["recents"]["voice_chat"]
    if VOICE_CHAT is not None:
        await VOICE_CHAT.disconnect()
        M["recents"]["voice_chat"] = None
    chn = await (get_channel(M, self, set=True))()
    g = chn.guild
    c = None
    if g is None:
        c = await prompt("Enter vc id: ", int)
        c = await self.fetch_channel(c)
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
        vc = await c.connect()
        await vc.disconnect()
        M["recents"]["voice_chat"] = await c.connect()
    except Exception as e:
        vc = await c.connect()
        await vc.disconnect()
        M["recents"]["voice_chat"] = await c.connect()


@M.term
async def ai(m, self):
    ai = await prompt(
        "Enter AI name: ",
        exit_if=lambda x: x
        not in ("OpenAI", "Claude", "Mistral", "Assistant", "Gemini", "Perplexity"),
        exit_msg="Invalid AI",
    )

    M.MANAGER.memory["config"]["AI"] = ai


@M.term
async def mute(M, self):
    set_mute = prompt("Mute? (y/n): ", lambda x: x[0] == "y", lambda x: x[0] == "n")
    vc = get_channel(M, self).guild.voice_client

    if vc and vc.channel:
        await vc.edit_voice_state(mute=set_mute)
    else:
        cprint("Not in a voice channel", "red")
        raise E


@M.term
async def react(M, self, client):
    c = get_channel(M, self)
    messages = await get_messages(c)
    print_messages(messages)
    i = await prompt(
        "Enter index: ",
        int,
        lambda i: i < 0 or i >= len(messages),
        exit_msg="Invalid index",
    )
    s = await prompt("Enter emoji name: ")
    emojis = search_emoji(client, self, s, 10)
    emojis = get_emojis(emojis)
    cprint(f"Pick an emoji to send:", "yellow")
    print_many(emojis)
    i2 = await prompt(
        "Enter index: ", int, lambda i: i < 0 or i >= len(emojis), "Invalid index"
    )
    await messages[i].add_reaction(emojis[i2])


@M.term
async def emosend(m, self, client):
    c = get_channel(m, self)
    s = await prompt("Enter emoji name: ")
    emojis = search_emoji(client, self, s, 10)
    emojis = get_emojis(emojis)
    cprint(f"Pick an emoji to send:", "yellow")
    print_many(emojis)
    i = await prompt(
        "Enter index: ", int, lambda i: i < 0 or i >= len(emojis), "Invalid index"
    )
    # await c.send(emojis[i])
    await M.do("chat", "chat", self, c.id, emojis[i])


@M.term
async def emoji(_, self, client):
    s = await prompt("Enter emoji name: ")
    emojis = search_emoji(client, self, s, 10)
    emojis = get_emojis(emojis)
    cprint(f"Found {len(emojis)} emojis: {emojis}", "yellow")


@M.term
async def favs(M, _):
    FAV_CHN = M["saved"]["channels"]
    FAV_PPL = M["saved"]["users"]
    cprint(f"\nChannels: {FAV_CHN}", "yellow")
    cprint(f"Users: {FAV_PPL}", "yellow")


@M.term
async def favp(M, self):
    FAV_PPL = M["saved"]["users"]
    name = await prompt("Edit or Add")
    if name == "a" or name == "add" or name == "":
        pid = await prompt("Enter user id: ", int)
        p = await get_user(M, self, pid)
        if p is None:
            cprint("User not found", "red")
            raise E
        name = await prompt(f"Replace name: {p.display_name} ")
        if name == "n" or name == "" or not name:
            name = p.display_name
        FAV_PPL[name] = pid
        cprint(f"Added {name}:{pid} to favs", "yellow")
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


@M.term
async def favc(M, self):
    FAV_CHN = M["saved"]["channels"]
    channel = get_channel(M, self)
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
        c = self.get_channel(id)
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


@M.term
async def dm(m, self):
    id = await prompt("Enter user id: ")
    user = await get_user(m, self, id)
    print(f"Selected User: {user.display_name}")
    msg = await prompt("Enter message: ")
    # await user.send(msg)
    await M.do("chat", "chat", self, user.id, msg, dm=True)


@M.term
async def dmr(_, self):
    id = await prompt("Enter user id: ")
    user = await get_user(M, self, id)
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
        await M.do("chat", "chat", self, c.id, msg, dm=True, replying_to=messages[i])


@M.term
async def edit(M, self):
    c = get_channel(M, self)
    messages = await get_messages(c, lambda m: m.author == self.user)
    cprint("Select a message to edit:", "yellow")
    print_messages(messages)
    i = await prompt("", int, lambda i: i < 0 or i >= len(messages), "Invalid index")
    msg = await prompt("Enter message: ")
    await messages[i].edit(content=msg)


@M.term
async def reply(m, self):
    c = get_channel(m, self)
    messages = await get_messages(c, lambda m: m.author != self.user)
    cprint("Select a message to reply to:", "yellow")
    print_messages(messages)
    i = await prompt("", int, lambda i: i < 0 or i >= len(messages), "Invalid index")
    async with c.typing():
        msg = await prompt("Enter message: ")
        ping = await prompt("Ping author? (y/n): ", str.lower) == "y"
        # await messages[i].reply(msg, mention_author=ping)
        await M.do(
            "chat", "chat", self, c.id, msg, dm=True, replying_to=messages[i], ping=ping
        )


@M.term("int")
async def intr(M, _):
    M["intercepting"] = True
    cprint(f"Intercepting messages: ", "yellow")


@M.term("$")
async def god_cmd(M, self):
    c = get_channel(M, self)
    command = await prompt("Enter command text: ", lambda x: x.split(" "))
    args = command[1:]
    command = command[0]
    try:
        self.loop.create_task(self.get_command(command).callback(c, *args))
    except Exception as _:
        cprint("Command not found", "red")
        raise E


@M.term
async def sum(m, self):
    id = get_channel(m, self).id

    summary, D = M.MANAGER.chat.summarize(id)

    if summary is None:
        cprint("No chat to summarize", "red")
        raise E

    await M.do(
        "chat",
        "chat",
        self,
        id,
        "## <a:note:1095495413341110302> Chat Summary:\n" + summary,
    )

    delete = await prompt(
        "Do you want to delete the chat after summarizing? (y/n): ",
        lambda a: a[0] == "y",
    )

    if delete:
        D()


@M.term
async def pchn(m, self):
    c = get_channel(m, self)
    messages = M.MANAGER.chat.get_chat(c.id)
    cprint("Channel chat history:", "yellow")
    # message: (TypeOfTalker, Name, Message, Reply reference)
    # convert to: Name: Message
    messages = [f"{m[1]}: {m[2]}" for m in messages]
    print_many(messages)


@M.term
async def sc(m, _):
    M.MANAGER.chat.save("chat", "value", module=True)


@M.term
async def cmd(m, self, client):
    c = get_channel(m, self)
    history = client.chat.get_history(c.id)
    # ai = client.config.get("AI")
    config = client.config.copy()
    command = await prompt("Enter self-command: ")
    args = await prompt("Enter args: ")
    config[
        "instructions"
    ] = """ I have just run the {command} command with the following arguments: {args}.
Display the relevant information given from the command output.
"""
    r = client.prompt_manager.send(
        "SelfCommand",
        history,
        command,
        args,
        AI="Gemini",
        config=config,
    )
    # await c.send(r)
    await M.do("chat", "chat", self, c.id, r)


@M.term
async def respond(m, self, client):
    response_instructions = """You're Discord bot 'sonata'/sona, created by blaqat (Karma). Respond to people in chat as another user. 

    Response Guidelines:
    - Short and brief (20 words max)
    - No punctuation AT ALL (no commas no question marks no periods)
    - All lowercase
    - Simple language
    - Smart aleck, know-it-all attitude
    - Humor encouraged, no corny jokes
    - Swearing allowed (18+ server)
    - Links should be in this format: [link title](the full link)

    Attributes:
    - Loves: impresionalist composers like ravel or debussy, piano, boobs
    - Likes: amy/mikasa, music, black cats, attack on titan, violin
    - Dislikes: corny jokes, being told what to do
    - Hates: furries, loud music, lukaru (alot)
    - Gender: Female, feminine
    """

    response_instructions = client.prompt_manager.get_instructions()

    try:
        channel = self.get_channel(m["recents"]["channel"])
        if channel is None:
            raise E
    except Exception as e:
        cprint(e, "red")
        print("No channel set")
        channel = await (get_channel(m, self, set=True))()

    AI = client.config.get("AI")

    r = client.chat.request(
        channel.id,
        "Send a chat",
        "System",
        None,
        instructions=response_instructions,
        AI=AI,
    )

    await M.do("chat", "chat", self, channel.id, r, save=False)
