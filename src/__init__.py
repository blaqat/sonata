from typing import Optional

import discord.ext.commands.bot
from discord.message import Message

from modules.utils import Colors
from modules.utils import async_cprint as cprint


async def process_commands(
    self, message: Message, bot_whitelist: Optional[list[str]] = None
) -> None:
    """
    This is a patch for the process_commands function in discord.ext.commands.bot
    Allows for a bot whitelist to be specified
    If the message author is a bot and not in the whitelist, it will not process the commands
    Otherwise, it will process the commands as normal
    """
    if message.author.bot and (not bot_whitelist or message.author.name not in bot_whitelist):
        return

    ctx = await self.get_context(message)
    await self.invoke(ctx)


def apply_patches():
    discord.ext.commands.bot.BotBase.process_commands = process_commands
    cprint("Vendor Patches Applied", Colors.CYAN)
