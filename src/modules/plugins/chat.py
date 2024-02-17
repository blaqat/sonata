import copy

import discord
from discord.ext import commands

from modules.AI_manager import AI_Manager
from modules.utils import (
    censor_message,
    cprint,
    cstr,
    get_full_name,
    runner,
    setter,
    settings,
)
import random

L, M, P = AI_Manager.init(
    lazy=True,
    config={
        "max_chats": 50,
        "summarize": False,
    },
)
__plugin_name__ = "chat"

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
    "tit",
    "tiddies",
    "penis",
    "boob",
    "puss",
    "nig",
    "kys",
    "retard",
    "sex",
    "porn",
    "kill yourself",
    "kill your self",
    "black people",
    "dick",
    "blow in from",
    "fuck me",
    "fuck you",
    "pussy",
    "kill themself",
    "kiya self",
    "shut the fuck up",
    "stfu",
    "stupid",
    "suck my",
    "suck me",
    "bitch",
}
CHANNEL_BLACKLIST = {
    743280190452400159,
    1175907292072398858,
    724158738138660894,
    725170957206945859,
}


async def chat_hook(Sonata, kelf: commands.Bot, message: discord.Message) -> None:
    if message.author.bot == True and message.author.name != "sonata":
        return
    message.content = message.content.replace('"', "'").replace("’", "'")
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
            cstr(str=get_full_name(message.author), style="cyan"),
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
        if message.content[0] == "$":
            split = message.content.split(" ")
            m = " ".join(split[1:])

        Sonata.chat.send(message.channel.id, "User", get_full_name(message.author), m)

    if message.attachments and not message.author.bot and len(message.attachments) > 0:
        attachment = message.attachments[0].url
        if attachment:
            message.content += f"\nAttachment: {attachment}"

    if message.reference is not None and not message.author.bot:
        # Check if reference is pointing to a message sent by the bot
        _ref = await message.channel.fetch_message(message.reference.message_id)
        if _ref.author.id == kelf.user.id:
            message.content = "$o " + message.content
            await kelf.process_commands(message)
            return
    if (
        "sonata" in message.content.lower()
        or "<@1187145990931763250>" in message.content.lower()
        or "sona " in message.content.lower()
        or " sona" in message.content.lower()
    ):
        # Remove the mention of sonata from the message
        message.content = message.content.replace("sonata", "")
        message.content = message.content.replace("<@1187145990931763250>", "")
        message.content = message.content.replace("sona ", "")
        message.content = message.content.replace(" sona", "")
        message.content = "$o " + message.content
    await kelf.process_commands(message)


@M.builder
def chat(self: AI_Manager):
    prompt_manager = self.prompt_manager

    class Chat:
        def get_chat(kelf, id):
            chat = self.get("chat")
            if chat.get(id) is None:
                chat[id] = []
            return chat[id]

        def send(
            kelf,
            id,
            message_type,
            author,
            message,
        ):
            chat = kelf.get_chat(id)
            self.set("chat", id, message_type, author, message)
            if len(chat) > self.config.get("max_chats") + 1 and self.config.get(
                "summarize"
            ):
                summary = self.do("chat", "summarize", id, self.get("config"))
                kelf.delete(id)
                kelf.send(id, "System", "PreviousChatSummary", summary)

        def request(
            kelf,
            id,
            message: str,
            *args,
            AI=self.config.get("AI"),
            error_prompt=None,
            **config,
        ):
            c = self.get("config")
            c.update(config)
            c["history"] = kelf.get_history(id)
            try:
                prompt = prompt_manager.get(
                    "Instructions", kelf.get_history(id), message, *args
                )

                response = self.do(
                    "chat",
                    "request",
                    prompt,
                    kelf.get_history(id),
                    message,
                    *args,
                    AI=AI,
                    config=c,
                )
            except Exception as e:
                if error_prompt is not None:
                    response = prompt_manager.send(error_prompt(e), AI=AI, config=c)
                else:
                    response = f"Response failed: {e}"
            finally:
                kelf.send(id, "Bot", self.name, response)
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


@M.prompt
def SummarizeChat(chat_log):
    return f"""Summarize the chat log in as little tokens as possible.
Use the following guidelines:
- Mention people by name or nickname.
- Don't just copy and paste the chat log. Summarize/paraphrase it.
Chat Log: {chat_log}
"""


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
)
def set_chat(M, chat_id, message_type, author, message):
    M["value"][chat_id].append((message_type, author, message))
    return (chat_id, message_type, author, message)


@M.effect("chat", "set")
def censor_chat(_, chat_id, message_type, author, message):
    return (chat_id, message_type, author, censor_message(message, BANNED_WORDS))
