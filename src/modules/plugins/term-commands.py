"""
This module is to handle the terminal override commands for the bot
"""

import discord
from modules.AI_manager import AI_Manager
from modules.utils import (
    async_cprint as cprint,
    async_print as print,
    setter,
)
import os
import asyncio
import aioconsole

L, M, P = AI_Manager.init(lazy=True, config={})
__plugin_name__ = "godmode"
__dependencies__ = ["chat"]


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


def __save_favs(M):
    with open("trm.favs", "w") as f:
        f.write(str(M["saved"]["channels"]) + "\n")
        f.write(str(M["saved"]["users"]) + "\n")


def __load_favs(M):
    try:
        if not os.path.exists("trm.favs"):
            with open("trm.favs", "w") as f:
                f.write(str(M["saved"]["channels"]) + "\n")
                f.write(str(M["saved"]["users"]) + "\n")
            return
        with open("trm.favs", "r") as f:
            lines = f.readlines()
            M["saved"]["channels"] = eval(lines[0])
            M["saved"]["users"] = eval(lines[1])
    except Exception as e:
        cprint("Error loading favs", "red")
        cprint(e, "red")


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


async def term_handler(A, client):
    while True:
        if A.get("termcmd", "intercepting", default=False):
            await asyncio.sleep(1)
            continue
        user_input = await prompt("Enter command: ")
        try:
            await A.do("termcmd", "run", user_input, client, A)
        except Exception as e:
            cprint(e, "red")


@M.mem(
    {},
    set=lambda M, name, func: setter(M["value"], name, func),
    save=__save_favs,
    load=__load_favs,
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
    return M["value"][name](*args[:num_required])


@M.effect("chat", "set", prepend=False)
def save_recent_message(_, chat_id, message_type, author, message, replying_to=None):
    M.get("termcmd", "recents")["channel"] = chat_id
    if message_type == "Bot":
        print("Saving recent message", chat_id, message)
        M.get("termcmd", "recents")["self_msg"] = chat_id
        print(M.get("termcmd", "recents")["self_msg"])
    return (chat_id, message_type, author, message, replying_to)


M.do("termcmd", "load")


@M.new_helper("term")
def term_command(F, name=None):
    M.set("termcmd", name or F.__name__, F)


"""
Helper Functions
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


def get_channel(M, self):
    print(M["recents"])
    c = self.get_channel(M["recents"]["pinned"] or M["recents"]["channel"])
    if c is None:
        cprint("No channel set", "red")
        raise E
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


"""
Commands
"""


@M.term
async def help(*_):
    print(
        """
        chn: Set channel
        reset: Reset channel
        god: Send message in channel
        dlr: Delete last message
        dlm: Delete message
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
        exit: Exit"""
    )


@M.term
async def chn(M, _):
    FAV_CHN = M["saved"]["channels"]
    c = await prompt("Enter channel id: ")
    if c == "fav":
        print_many(FAV_CHN.keys())
        c = await prompt(
            "Enter fav name: ", FAV_CHN.get, lambda x: x is None, "Fav not found"
        )
        print(FAV_CHN, c)
    M["recents"]["pinned"] = int(c)


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
    else:
        if name not in FAV_CHN:
            cprint("Fav not found", "red")
            raise E
        id = await prompt(f"Replace id: {FAV_CHN[name]}")
        if id == "n" or id == "" or not id:
            id = FAV_CHN[name]
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
async def dmr(m, self):
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
async def cmd(m, self, client):
    c = get_channel(m, self)
    history = client.chat.get_history(c.id)
    ai = client.config.get("AI")
    config = client.get("config")
    command = await prompt("Enter self-command: ")
    args = await prompt("Enter args: ")
    r = client.prompt_manager.send(
        "SelfCommand",
        history,
        command,
        args,
        AI=ai,
        config=config,
    )
    # await c.send(r)
    await M.do("chat", "chat", self, c.id, r)
