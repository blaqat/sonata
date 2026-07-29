from typing import Optional, Union

import discord.ext.commands.bot
from discord.message import Message

from modules.activation_trace import get_active_activation_trace
from modules.utils import Colors
from modules.utils import async_cprint as cprint


async def process_commands(
    self,
    message: Message,
    bot_whitelist: Optional[list[Union[str, int]]] = None,
) -> None:
    """
    This is a patch for the process_commands function in discord.ext.commands.bot
    Allows for a bot whitelist to be specified
    If the message author is a bot and not in the whitelist, it will not process the commands
    Otherwise, it will process the commands as normal
    """
    trace = get_active_activation_trace()
    author_allowed = not message.author.bot or bool(
        bot_whitelist
        and (
            message.author.name in bot_whitelist
            or message.author.id in bot_whitelist
        )
    )
    if trace:
        trace.stage(
            "discord.author_gate.checked",
            author_is_bot=message.author.bot,
            allowed=author_allowed,
        )

    if not author_allowed:
        if trace:
            trace.stage("discord.author_gate.rejected")
        return

    ctx = await self.get_context(message)
    if trace:
        trace.stage(
            "discord.command.context_resolved",
            command=getattr(getattr(ctx, "command", None), "qualified_name", None),
            valid=getattr(ctx, "valid", False),
        )
        trace.stage("discord.command.invoke.started")
    await self.invoke(ctx)
    if trace:
        trace.stage("discord.command.invoke.completed")


def apply_patches():
    discord.ext.commands.bot.BotBase.process_commands = process_commands
    cprint("Vendor Patches Applied", Colors.CYAN)
