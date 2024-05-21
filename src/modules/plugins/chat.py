"""
Chat
----
This plugin is responsible for handling chat messages and processing them through the AI model.
In addition, it provides a way to store and retrieve chat logs for summarization and other purposes.
Also, it provides a way to send messages to a specific channel or user.
"""

import copy

import discord
from discord.ext import commands

from modules.AI_manager import AI_Manager
from modules.utils import (
    censor_message,
    async_print as print,
    async_cprint as cprint,
    cstr,
    get_full_name,
    runner,
    setter,
    settings,
    has_inside,
)
import random
import re

L, M, P = AI_Manager.init(
    lazy=True,
    config={
        "max_chats": 50,
        "summarize": False,
        "auto": "o",
        "view_replies": True,
    },
)
__plugin_name__ = "chat"


"""
Hooks    -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""

# TODO: Make new hook system for general hooks that can b iterated on in the main loop


async def dm_hook(Sonata, kelf: commands.Bot, message: discord.Message) -> None:
    AI = Sonata.config.get("auto")
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
    ) and not message.author.bot:
        message.content = message.content.replace("sonata", "")
        message.content = message.content.replace("<@1187145990931763250>", "")
        message.content = message.content.replace("sona ", "")
        message.content = message.content.replace(" sona", "")

    # Format and display the message
    print(
        "  {0}: {1}".format(
            cstr(str=get_full_name(message), style="cyan"),
            censor_message(
                message.content.replace("\n", "\n\t"),
                BANNED_WORDS,
            ),
        )
    )

    # Prepare the memory text
    memory_text = message.author.name

    # Process user messages
    if not message.author.bot and message.content:
        m = message.content
        if message.content[0] == "$":
            return await kelf.process_commands(message)

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
    #
    # Handle message attachments
    image_types = ["png", "jpg", "jpeg", "webp"]
    if message.attachments and not message.author.bot and len(message.attachments) > 0:
        # attachment = [x.url for x in message.attachments]
        attachment = []
        not_grabbed = []
        for x in message.attachments:
            if has_inside(x.url, image_types):
                attachment.append(x.url)
            else:
                not_grabbed.append(x.url)
        Sonata.config.set(images=attachment)
        if len(not_grabbed) > 0:
            message.content += f"\nAttachment: {not_grabbed}"
        # attachment = message.attachments[0].url
        # if attachment:
        #     message.content += f"\nAttachment: {attachment}"

    message.content = f"${AI} " + message.content
    # Process the message
    await kelf.process_commands(message)


async def chat_hook(Sonata, kelf: commands.Bot, message: discord.Message) -> None:
    AI = Sonata.config.get("auto")
    USE_REPLY_REF = Sonata.config.get("view_replies")
    if message.author.bot == True and message.author.name != "sonata":
        return
    message.content = message.content.replace('"', "'").replace("’", "'")

    if message.guild == None:  # Ignore DMS
        return

    _guild_name = message.guild.name
    _channel_name = message.channel.name
    _name = (
        message.author.nick if "nick" in dir(message.author) else message.author.name
    )
    _ref = None
    if _name and _name == "None" or not _name:
        _name = message.author.name

    if Sonata.do("chat", "validate", message.channel.id):
        return

    if _guild_name != kelf.current_guild:
        cprint("\n" + _guild_name.lower(), "purple", "_")
        kelf.current_guild = _guild_name

    if _channel_name != kelf.current_channel:
        cprint("#" + _channel_name, "green", end=" ")
        print(f"({message.channel.id})")
        kelf.current_channel = _channel_name

    print(
        "  {0}: {1}".format(
            cstr(str=get_full_name(message), style="cyan"),
            censor_message(
                message.content.replace("\n", "\n\t"),
                BANNED_WORDS,
            ),
        )
    )

    memory_text = message.author.name + (
        f" (Nickname {_name})" if _name != message.author.name else ""
    )

    memory_text = memory_text.strip()
    if message.author.bot == False and len(message.content) > 0:
        m = message.content
        # Remove command from message
        if message.content[0] == "$":
            split = message.content.split(" ")
            if len(split[0]) == 1:
                m = " ".join(split[1:])

        # Check for message references (replies)
        _ref = (
            message.reference is not None
            and await message.channel.fetch_message(message.reference.message_id)
            or None
        )
        _ref = _ref and (_ref.author.name, _ref.content) or None
        if not USE_REPLY_REF:
            _ref = None
        message.content = Sonata.chat.send(
            message.channel.id, "User", get_full_name(message), m, _ref
        )
        if message.content is None:
            return

    # TODO: Add way to store attachments since can send them in message now
    # Add way to convert stickers into images
    # Add way to convert any image link into same system as attched images
    #
    # Handle message attachments
    image_types = ["png", "jpg", "jpeg", "webp"]
    if message.attachments and not message.author.bot and len(message.attachments) > 0:
        # attachment = [x.url for x in message.attachments]
        attachment = []
        not_grabbed = []
        for x in message.attachments:
            if has_inside(x.url, image_types):
                attachment.append(x.url)
            else:
                not_grabbed.append(x.url)
        Sonata.config.set(images=attachment)
        if len(not_grabbed) > 0:
            message.content += f"\nAttachment: {not_grabbed}"
        # attachment = message.attachments[0].url
        # if attachment:
        #     message.content += f"\nAttachment: {attachment}"

    # Pass referenced messages to AI
    if message.reference is not None and not message.author.bot:
        # Check if reference is pointing to a message sent by the bot
        _ref = await message.channel.fetch_message(message.reference.message_id)
        if _ref.author.id == kelf.user.id:
            message.content = f"${AI} " + message.content
            await kelf.process_commands(message)
            return

    # if (
    #     "sonata" in message.content.lower()
    #     or "<@1187145990931763250>" in message.content.lower()
    #     or "sona " in message.content.lower()
    #     or " sona" in message.content.lower()
    # ) and not message.author.bot:
    #     message.content = message.content.replace("sonata", "")
    #     message.content = message.content.replace("<@1187145990931763250>", "")
    #     message.content = message.content.replace("sona ", "")
    #     message.content = message.content.replace(" sona", "")
    #     message.content = f"${AI} " + message.content

    sonata_names = {"sonata", "sona"}
    sonata_exp = re.compile(
        f"<@{kelf.user.id}>|" + "|".join([f"\\b{name}\\b" for name in sonata_names]),
        re.IGNORECASE,
    )
    if not message.author.bot and sonata_exp.search(message.content):
        message.content = sonata_exp.sub("", message.content).strip()
        message.content = f"${AI} {message.content}"

    await kelf.process_commands(message)


@M.effect("chat", "set", prepend=True)
def censor_chat(_, chat_id, message_type, author, message, replying_to=None):
    return (
        chat_id,
        message_type,
        author,
        censor_message(message, BANNED_WORDS),
        replying_to,
    )


"""
Helper Functions -----------------------------------------------------------------------------------------------------------------------------------------------------------
"""


async def __chat(M, bot, channel_id, message, dm=False, replying_to=None, ping=False):
    if replying_to is not None:
        await replying_to.reply(message, mention_author=ping)
    elif dm:
        await bot.get_user(channel_id).send(message)
    else:
        await bot.get_channel(channel_id).send(message)

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
    "balls",
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
}

# TODO: Convert channel blacklist into more ergonomic thing
# 1. Should control if bot can speak in
# 2. Should control if bot speaks to all messages or just invokations
# 3. Should control what commands bot can do
# etc
CHANNEL_BLACKLIST = {
    743280190452400159,
    1175907292072398858,
    724158738138660894,
    725170957206945859,
}


@M.builder
def chat(self: AI_Manager):
    prompt_manager = self.prompt_manager

    # TODO: Make way to translate history into proper chat log format for each AI
    #
    class Chat:
        def get_chat(kelf, id):
            chat = self.get("chat")
            if chat.get(id) is None:
                chat[id] = []
            return chat[id]

        def summarize(kelf, id):
            config = self.get("config")
            config["instructions"] = " "
            summary = self.do("chat", "summarize", id, config)

            def deleter():
                kelf.delete(id)
                kelf.send(id, "System", "PreviousChatSummary", summary, None)

            return summary, deleter

        def send(kelf, id, message_type, author, message, replying_to=None):
            chat = kelf.get_chat(id)
            a = self.set("chat", id, message_type, author, message, replying_to)
            if len(chat) > self.config.get("max_chats") + 1 and self.config.get(
                "summarize"
            ):
                kelf.summarize(id)[1]()  # Summarizes and deletes chat
            return a[3]

        def request(
            kelf,
            id,
            message: str,
            user_name: str,
            replying_to=None,
            *args,
            AI=self.config.get("AI"),
            error_prompt=None,
            **config,
        ):
            # TODO: Add way to store attachments since can send them in message now
            # They are accessed in config['images']
            response = None
            chat_history = kelf.get_history(id)
            c = self.get("config")
            c["history"] = chat_history
            c["instructions"] = prompt_manager.get_instructions()
            c["channel_id"] = id
            c.update(config)
            try:
                if "using_assistant" not in c and prompt_manager.exists("History"):
                    response = self.do(
                        "chat",
                        "request",
                        prompt_manager.prompts["History"](chat_history)
                        + prompt_manager.prompts["Message"](
                            user_name, message, replying_to
                        )
                        + "\nsonata:",
                        # kelf.get_history(id),
                        # user_name,
                        # message,
                        # replying_to,
                        *args,
                        AI=AI,
                        config=c,
                    )
                else:
                    response = self.do(
                        "chat",
                        "request",
                        prompt_manager.prompts["Message"],
                        # kelf.get_history(id),
                        user_name,
                        message,
                        replying_to,
                        *args,
                        AI=AI,
                        config=c,
                    )

                kelf.send(id, "Bot", self.name, response, replying_to)
                return response
            except Exception as e:
                # if error_prompt is not None:
                #     response = prompt_manager.send(
                #         str(error_prompt(e, message)), AI=AI, config=c
                #     )
                #     if response is None:
                #         response = (
                #             f"Response failed in using the error prompt silly :3: {e}"
                #         )
                # else:
                response = f"{e}"
                kelf.send(id, "Bot", self.name, response, replying_to)
                return response

        def get_history(
            kelf,
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
                return kelf.get_chat(chat_id)
            else:
                # human_messages: User, ai_messages: Bot, system_messages: System
                return [
                    m
                    for m in kelf.get_chat(chat_id)
                    if m[0]
                    in [
                        human_messages and "User",
                        ai_messages and "Bot",
                        system_messages and "System",
                    ]
                ]

        def delete(
            kelf,
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
                self.reset("chat", chat_id)
            else:
                # human_messages: User, ai_messages: Bot, system_messages: System
                self.get("chat")[chat_id] = kelf.get_history(
                    chat_id, human_messages, ai_messages, system_messages
                )

    return Chat


@M.mem(
    {},
    default_value=[],
    banned_words=BANNED_WORDS,
    black_list=CHANNEL_BLACKLIST,
    r=lambda M, chat_id: setter(M["value"], chat_id, copy.deepcopy(M["default_value"])),
    request=lambda _, *args, **kwargs: P.send(*args, **kwargs),
    summarize=lambda M, id, config: P.send(
        "SummarizeChat", M["value"][id], AI=config["AI"], config=config
    ),
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


@M.prompt
def SummarizeChat(chat_log):
    return f"""Summarize the chat log in as little tokens as possible.
Use the following guidelines:
- Mention people by name, not nickname. 
- Don't just copy and paste the chat log. Summarize/paraphrase it.
- If there is a PreviousChatSummary, include it in the summary.
Chat Log: {chat_log}
"""
