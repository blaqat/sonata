"""
Chat
----
This plugin is responsible for handling chat messages and processing them through the AI model.
In addition, it provides a way to store and retrieve chat logs for summarization and other purposes.
Also, it provides a way to send messages to a specific channel or user.
"""

# TODO: Make  message class
# Message class will have attributes such as:
# Author, Content, Attachments,  Channel, Guild, etc
# As well as links to previous messages & reply chains
# Public fields for history and reply chains with methods for getting n number of messages before or after
# Also will talk to discord api to find more messages
# ______________________________
# Message class will also have translators to convert to differe ai api chat history formats

import copy

import discord
from discord.ext import commands
from requests import get

from modules.AI_manager import AI_Manager
from modules.utils import (
    censor_message,
    async_print as print,
    async_cprint as cprint,
    cstr,
    get_full_name,
    setter,
    settings,
    has_inside,
    get_reference_message as get_ref,
    get_reference_chain as get_ref_chain,
    tenor_get_dl_url,
    get_trace,
)
import random
import re
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(
    lazy=True,
    config={
        "max_chats": 50,
        "summarize": False,
        "auto": "o",
        "view_replies": True,
        "ignore": [],
        "response_map": {},  # {userName: (response, random chance)}
        "bot_whitelist": [],
        "censor": True,
    },
)
__plugin_name__ = "chat"


"""
Hooks    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


# TODO: Make new hook system for general hooks that can b iterated on in the main loop
# https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645122
async def dm_hook(Sonata, self: commands.Bot, message: discord.Message) -> None:
    """Handle direct messages (DMs) sent to the bot"""
    AI = Sonata.config.get("auto")
    CENSOR = Sonata.config.get("censor", True)
    # AI = Sonata.config.get("auto")
    USE_REPLY_REF = Sonata.config.get("view_replies")
    # Ignore messages from bots except 'sonata'
    if message.author.bot and message.author.name != "sonata":
        return

    # Replace certain characters in message content
    message.content = message.content.replace('"', "'").replace("’", "'")

    # Process only direct messages (DMs)
    if message.guild is not None:  # Ignore non-DMs
        return

    _name = message.author.name
    if _name == "None" or not _name:
        _name = message.author.name

    # Validate the message for processing
    if Sonata.do("chat", "validate", message.channel.id):
        return

    # Handle specific keywords in message content
    if (
        "sonata" in message.content.lower()
        or "<@1187145990931763250>" in message.content.lower()
        or "sona " in message.content.lower()
        or " sona" in message.content.lower()
        or "ソナ" in message.content.lower()
        or "ソナタ" in message.content.lower()
    ) and not message.author.bot:
        message.content = message.content.replace("sonata", "")
        message.content = message.content.replace("<@1187145990931763250>", "")
        message.content = message.content.replace("sona ", "")
        message.content = message.content.replace(" sona", "")

    # Format and display the message

    print(
        "  {0}: {1}".format(
            cstr(str=get_full_name(message), style=message.author.color),
            CENSOR
            and censor_message(
                message.content.replace("\n", "\n\t"),
                BANNED_WORDS,
            )
            or message.content.replace("\n", "\n\t"),
        )
    )

    # Prepare the memory text
    memory_text = message.author.name

    # Process user messages
    if not message.author.bot and message.content:
        m = message.content
        if message.content[0] == "$":
            return await self.process_commands(message)

        # Check for message references (replies)
        _ref = (
            message.reference
            and await message.channel.fetch_message(message.reference.message_id)
            or None
        )
        _ref = _ref and (_ref.author.name, _ref.content) or None
        if not USE_REPLY_REF:
            _ref = None

        # Send the message for processing
        message.content = Sonata.chat.send(
            message.channel.id, "User", get_full_name(message), m, _ref
        )
        if message.content is None:
            return

    # TODO: Add way to store attachments since can send them in message now
    # Add way to convert stickers into images
    # Add way to convert any image link into same system as attched images
    # https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645315
    #
    #
    # Handle message attachments
    #
    # image_types = ["png", "jpg", "jpeg", "webp"]
    # if message.attachments and not message.author.bot and len(message.attachments) > 0:
    #     # attachment = [x.url for x in message.attachments]
    #     attachment = []
    #     not_grabbed = []
    #     for x in message.attachments:
    #         if has_inside(x.url, image_types):
    #             attachment.append(x.url)
    #         else:
    #             not_grabbed.append(x.url)
    #
    #     Sonata.config.set(images=attachment)
    #     if len(not_grabbed) > 0:
    #         message.content += f"\nAttachment: {not_grabbed}"
    # attachment = message.attachments[0].url
    # if attachment:
    #     message.content += f"\nAttachment: {attachment}"

    if not message.author.bot:
        attachments = []
        not_grabbed = []
        image_types = ["png", "jpg", "jpeg", "webp"]

        urls = re.findall(r"http\S+", message.content)
        for url in urls:
            if has_inside(url, image_types):
                if "tenor.com" in url:
                    url = tenor_get_dl_url(
                        url, settings.TENOR_G, "tinywebppreview_transparent"
                    )
                attachments.append(url)
                message.content = message.content.replace(url, "")
            else:
                not_grabbed.append(url)

        if message.attachments and len(message.attachments) > 0:
            for x in message.attachments:
                if has_inside(x.url, image_types):
                    attachments.append(x.url)
                else:
                    not_grabbed.append(x.url)

        if len(attachments) > 0:
            # FIXME: Images being queued and only loaded when the next @sonata happens
            # Handle message attachments
            images = Sonata.config.get("images", {})
            images[message.channel.id] = attachments
            Sonata.config.set(images=images)

        if len(not_grabbed) > 0:
            message.content += f"\nAttachment: {not_grabbed}"
        # attachment = message.attachments[0].url
        # if attachment:
        #     message.content += f"\nAttachment: {attachment}"

    message.content = f"${AI} " + message.content
    # Process the message
    await self.process_commands(message)


async def chat_hook(Sonata, self: commands.Bot, message: discord.Message) -> None:
    """Handle messages sent in guild channels"""
    AI = Sonata.config.get("auto")
    CENSOR = Sonata.config.get("censor", True)
    USE_REPLY_REF = Sonata.config.get("view_replies")
    IGNORE_LIST = Sonata.config.get("ignore", [])
    RESPONSES = Sonata.config.get("response_map", {})
    WHITELIST = Sonata.config.get("bot_whitelist", [])
    VALID_USER = (
        message.author.bot
        and (message.author.name in WHITELIST or message.author.id in WHITELIST)
        or not message.author.bot
    )
    IS_SONATA = message.author.bot and message.author.name == "sonata"

    if message.author.bot and message.author.name != "sonata" and not VALID_USER:
        # cprint(f"Ignoring: {message.author.id}: {message.content}", "red")
        return

    _name = (
        message.author.nick if "nick" in dir(message.author) else message.author.name
    )
    if _name and _name == "None" or not _name:
        _name = message.author.name

    # Hating Arc
    if _name.lower() in IGNORE_LIST:
        cprint(f"Ignoring: {message.author.name}: {message.content}", "red")
        return

    message.content = message.content.replace('"', "'").replace("’", "'")

    if message.guild == None:  # Ignore DMS
        return

    _guild_name = message.guild.name
    _channel_name = message.channel.name
    message_reference = None

    if Sonata.do("chat", "validate", message.channel.id):
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
            cstr(str=get_full_name(message), style=message.author.color),
            CENSOR
            and censor_message(
                message.content.replace("\n", "\n\t"),
                BANNED_WORDS,
            )
            or message.content.replace("\n", "\n\t"),
        )
    )

    memory_text = message.author.name + (
        f" (Nickname {_name})" if _name != message.author.name else ""
    )

    message_reference = await get_ref(message)

    message_reference_id = (
        message_reference is not None and message_reference.author.id or None
    )

    if USE_REPLY_REF and message_reference is not None:
        message_reference = await get_ref_chain(message_reference, include_message=True)
        # cprint(message_reference, "green")
        # print("  Reference Chain:", _ref_chain)
        # message_reference = (
        #     message_reference
        #     and (message_reference.author.name, message_reference.content)
        #     or None
        # )
    else:
        message_reference = None

    memory_text = memory_text.strip()

    # Process user messages
    if VALID_USER and len(message.content) > 0:
        # m = message.content
        # Remove command from message
        # if message.content[0] == "$":
        #     split = message.content.split(" ")
        #     if len(split[0]) == 1:
        #         m = " ".join(split[1:])

        Sonata.chat.send(
            message.channel.id, "User", get_full_name(message), message.content
        )

        if message.content is None:
            return

    # TODO: Add way to store attachments since can send them in message now
    # Add way to convert stickers into images
    #
    if VALID_USER:
        attachments = []
        not_grabbed = []
        image_types = ["png", "jpg", "jpeg", "webp"]
        # HACK: Lets claude read gifs
        # if M.MANAGER.config.get("AI", "Gemini") == "Claude":
        #     image_types.append("gif")
        #     image_types.append("mp4")

        urls = re.findall(r"http\S+", message.content)
        for url in urls:
            if has_inside(url, image_types):
                if "tenor.com" in url:
                    url = tenor_get_dl_url(
                        url, settings.TENOR_G, "tinywebppreview_transparent"
                    )
                attachments.append(url)
                message.content = message.content.replace(url, "")
            else:
                not_grabbed.append(url)

        if message.attachments and len(message.attachments) > 0:
            for x in message.attachments:
                if has_inside(x.url, image_types):
                    attachments.append(x.url)
                else:
                    not_grabbed.append(x.url)

        if len(attachments) > 0:
            # FIXME: Images being queued and only loaded when the next @sonata happens
            # Handle message attachments
            images = Sonata.config.get("images", {})
            images[message.channel.id] = attachments
            Sonata.config.set(images=images)

        if len(not_grabbed) > 0:
            message.content += f"\nAttachment: {not_grabbed}"
        # attachment = message.attachments[0].url
        # if attachment:
        #     message.content += f"\nAttachment: {attachment}"

    # Pass referenced messages to AI
    if message_reference_id is not None and VALID_USER:
        # Check if reference is pointing to a message sent by the bot
        # message_reference = await message.channel.fetch_message(
        #     message.reference.message_id
        # )
        if message_reference_id == self.user.id:
            if (
                message.author.name in RESPONSES
                or message.author.nick
                and message.author.nick in RESPONSES
            ):
                chance, response = RESPONSES.get(
                    message.author.name, RESPONSES.get(message.author.nick)
                )
                if random.random() < chance:
                    await message.reply(response, mention_author=False)
                    Sonata.chat.send(message.channel.id, "Bot", "sonata", response)
                    message.content += "1"
            else:
                message.content += "0"
            message.content = f"${AI} " + message.content
            await self.process_commands(message, bot_whitelist=WHITELIST)
            return
        #
        # await self.process_commands(message)
        # return

    sonata_names = {"sonata", "sona", "ソナ", "ソナタ"}
    sonata_exp = re.compile(
        f"<@{self.user.id}>|" + "|".join([f"\\b{name}\\b" for name in sonata_names]),
        re.IGNORECASE,
    )
    if VALID_USER and sonata_exp.search(message.content):
        message.content = sonata_exp.sub("", message.content).strip()
        message.content = f"${AI} {message.content}"
        if _name in RESPONSES:
            chance, response = RESPONSES.get(
                message.author.name, RESPONSES.get(message.author.nick)
            )
            if random.random() < chance:
                await message.reply(response, mention_author=False)
                Sonata.chat.send(message.channel.id, "Bot", "sonata", response)
                message.content += "1"
        else:
            message.content += "0"

    await self.process_commands(message, bot_whitelist=WHITELIST)


@MANAGER.effect("chat", "set", prepend=True)
def censor_chat(_, chat_id, message_type, author, message, replying_to=None):
    """Effect to censor messages before storing them in chat history"""
    CENSOR = CONTEXT.plugin_config.get("censor", True)
    return (
        chat_id,
        message_type,
        author,
        CENSOR and censor_message(message, BANNED_WORDS) or message,
        replying_to,
    )


@MANAGER.effect("chat", "set", prepend=True)
def timestamp_chat(_, chat_id, message_type, author, message, replying_to=None):
    time = discord.utils.utcnow().astimezone(EASTERN)
    timestamped_message = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    return (
        chat_id,
        message_type,
        author,
        timestamped_message,
        replying_to,
    )


"""
Helper Functions -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


async def __chat(
    M, bot, channel_id, message, dm=False, replying_to=None, ping=False, save=True
):
    """
    Send a message to a specific channel or user, with options for DM, replying, and saving
    """
    if replying_to is not None:
        await replying_to.reply(message, mention_author=ping)
    elif dm:
        await bot.get_user(channel_id).send(message)
    else:
        await bot.get_channel(channel_id).send(message)

    if save:
        M["set"](
            M,
            channel_id,
            "Bot",
            bot.user.name,
            message,
            (replying_to.author.name, replying_to.content) if replying_to else None,
        )


"""
Setup    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

BANNED_WORDS = {
    "jerking it",
    "jerking off",
    "cunt",
    "cock",
    # "balls",
    "aggin",
    "reggin",
    "nigger",
    "rape",
    # "tit",
    "tiddies",
    "penis",
    # "boob",
    "puss",
    "nig",
    "kys",
    "retard",
    # "sex",
    # "porn",
    "kill yourself",
    "kill your self",
    "black people",
    # "dick",
    "blow in from",
    "fuck me",
    "fuck you",
    # "pussy",
    "kill themself",
    "kiya self",
    "shut the fuck up",
    "stfu",
    # "stupid",
    "suck my",
    "suck me",
    "bitch",
    "ME OFF",
}

# TODO: Convert channel blacklist into more ergonomic thingy
# 1. Should control if bot can speak in
# 2. Should control if bot speaks to all messages or just invokations
# 3. Should control what commands bot can do
# etc
# https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645262
CHANNEL_BLACKLIST = {
    # 743280190452400159,
    1175907292072398858,
    724158738138660894,
    725170957206945859,
}


@MANAGER.builder
def chat(sona: AI_Manager):
    """
    Chat plugin for handling messages and interactions
    """
    prompt_manager = sona.prompt_manager

    # TODO: Make way to translate history into proper chat log format for each AI
    # https://github.com/users/bIaqat/projects/1/views/1?pane=issue&itemId=65645361
    #
    class Chat:
        def get_chat(self, id):
            """Retrieve the chat history for a given chat ID."""
            chat = sona.get("chat")
            if chat.get(id) is None:
                chat[id] = []
            return chat[id]

        def summarize(self, id):
            """Summarize the chat history for a given chat ID and provide a deleter function."""
            config = sona.get("config")
            config["instructions"] = ""

            summary = sona.do("chat", "summarize", id, config)

            def deleter():
                try:
                    self.delete(id)
                    self.send(id, "System", "PreviousChatSummary", summary, None)
                except:
                    cprint("Error deleting chat after summarization", "red")

            return summary, deleter

        def send(self, id, message_type, author, message, replying_to=None):
            """Send a message to a specific chat ID and store it in the chat history."""
            chat = self.get_chat(id)
            # Adds message to chat history + mutates by any effects e.g censoring
            a = sona.set("chat", id, message_type, author, message, replying_to)

            try:
                if len(chat) > sona.config.get("max_chats") + 1 and sona.config.get(
                    "summarize"
                ):
                    self.summarize(id)[1]()  # Summarizes and deletes chat
            except Exception as e:
                cprint(f"Error in chat send: {e}", "red")
                return a[3]

            return a[3]  # Return the message sent

        def request(
            self,
            id,
            message: str,
            user_name: str,
            replying_to=None,
            *args,
            AI=sona.config.get("AI"),
            error_prompt=None,
            save=True,
            **config,
        ):
            """Request a response from the AI for a given message and chat ID."""
            # TODO: Add way to store attachments since can send them in message now
            # They are accessed in config['images']
            # https://github.com/users/blaqat/projects/1/views/1?pane=issue&itemId=65645315
            response = None
            chat_history = self.get_history(id)
            new_c = {}
            c = sona.get("config")
            new_c.update(c)
            new_c["history"] = chat_history
            new_c["instructions"] = prompt_manager.get_instructions()
            new_c["channel_id"] = id
            # Get Images for this channel
            new_c["images"] = ((c if c else {}).get("images") or {}).get(id, None)
            new_c.update(config)
            try:
                if "using_assistant" not in new_c and prompt_manager.exists("History"):
                    response = sona.do(
                        "chat",
                        "request",
                        prompt_manager.prompts["History"](chat_history)
                        + prompt_manager.prompts["Message"](
                            user_name, message, replying_to
                        )
                        + "\nJust state your message here: ",
                        *args,
                        AI=AI,
                        config=new_c,
                    )
                else:
                    response = sona.do(
                        "chat",
                        "request",
                        prompt_manager.prompts["MessageAssistant"],
                        user_name,
                        message,
                        *args,
                        AI=AI,
                        config=new_c,
                    )

                if save:
                    self.send(id, "Bot", sona.name, response, replying_to)
                # HACK: This is a hack to get the images from the config to clear
                (c.get("images") or {})[id] = None
                (sona.config.get().get("images") or {})[id] = None
                (sona.memory["config"]["value"].get("images") or {})[id] = None
                return response
            except Exception as e:
                # response = f"{e}"
                # return response
                # self.send(id, "Bot", sona.name, response, replying_to)
                cprint(f"Error in chat request: {get_trace()}", "red")
                raise e

        def get_history(
            self,
            chat_id,
            human_messages=None,
            ai_messages=None,
            system_messages=None,
        ):
            if (
                human_messages is None
                and ai_messages is None
                and system_messages is None
            ):
                return self.get_chat(chat_id)
            else:
                # human_messages: User, ai_messages: Bot, system_messages: System
                return [
                    m
                    for m in self.get_chat(chat_id)
                    if m[0]
                    in [
                        human_messages and "User",
                        ai_messages and "Bot",
                        system_messages and "System",
                    ]
                ]

        def delete(
            self,
            chat_id,
            human_messages=True,
            ai_messages=True,
            system_messages=True,
        ):
            if (
                human_messages is True
                and ai_messages is True
                and system_messages is True
            ):
                sona.reset("chat", chat_id)
            else:
                # human_messages: User, ai_messages: Bot, system_messages: System
                sona.get("chat")[chat_id] = self.get_history(
                    chat_id, human_messages, ai_messages, system_messages
                )

    return Chat


def Summarize(M, id, config):
    config[
        "instructions"
    ] = f"""Summarize the chat log in as little tokens as possible.
Use the following guidelines:
- Mention people by name, not nickname.
- Don't just copy and paste the chat log. Summarize/paraphrase it.
- If there is a PreviousChatSummary, include it as much as possible into the new summary as it will be replaced with this afterwards.
"""
    try:
        ti = config.get("images")
        config["images"] = None
        sum = PROMPT_MANAGER.send(
            lambda chat: f"""Chat Log: {chat}""",
            M["value"][id],
            AI=config["AI"],
            config=config,
        )
        config["images"] = ti
        return sum
    except Exception as e:
        cprint(f"Error in chat summarize: {e}", "red")
        raise e


# Chat Plugin Instantiation
@MANAGER.mem(
    {},
    default_value=[],
    banned_words=BANNED_WORDS,
    black_list=CHANNEL_BLACKLIST,
    r=lambda M, chat_id: setter(M["value"], chat_id, copy.deepcopy(M["default_value"])),
    request=lambda _, *args, **kwargs: PROMPT_MANAGER.send(*args, **kwargs),
    summarize=Summarize,
    validate=lambda M, id: id in M["black_list"],
    blacklist=lambda M, id: M["black_list"].add(id),
    hook=chat_hook,
    dm_hook=dm_hook,
    chat=__chat,
)
def set_chat(M, chat_id, message_type, author, message, replying_to=None):
    if M["value"].get(chat_id) is None:
        M["value"][chat_id] = []
    M["value"][chat_id].append((message_type, author, message, replying_to))
    return (chat_id, message_type, author, message, replying_to)


"""
Prompts    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


@MANAGER.prompt
def OldSummarizeChat(chat_log):
    return f"""Summarize the chat log in as little tokens as possible.
Use the following guidelines:
- Mention people by name, not nickname.
- Don't just copy and paste the chat log. Summarize/paraphrase it.
- If there is a PreviousChatSummary, include it in the summary.
Chat Log: {chat_log}
"""
