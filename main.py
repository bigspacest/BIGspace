"""
main.py
-------
Bot entry point. Loads environment variables, sets up the prefix
(case-insensitive), registers the cogs, syncs slash commands, and
starts the Flask keep-alive server.
"""

import os
import re
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from keep_alive import keep_alive

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
RAW_PREFIX = os.getenv("PREFIX", "?")

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("bot")


def case_insensitive_prefix(bot: commands.Bot, message: discord.Message):
    """
    Allows the prefix to be used in any combination of upper/lowercase
    letters: ?lock, ?LOCK, ?Lock, etc, all work the same way.
    """
    prefix = re.escape(RAW_PREFIX)
    match = re.match(f"^{prefix}", message.content, re.IGNORECASE)
    if match:
        return message.content[: match.end()]
    # If it doesn't match the prefix as-is, fall back to the normal prefix
    # (discord.py will use this for the standard mention check, etc)
    return commands.when_mentioned_or(RAW_PREFIX)(bot, message)


intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.moderation = True  # needed to see/apply member timeouts (mutes)

bot = commands.Bot(command_prefix=case_insensitive_prefix, intents=intents, help_command=None)

COGS = [
    "welcome",
    "bot_setup",
    "automod",
    "moderation",
]


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        log.info(f"Slash commands synced: {len(synced)}")
    except Exception as e:
        log.error(f"Error syncing slash commands: {e}")
    await bot.change_presence(activity=discord.Game(name=f"{RAW_PREFIX}cmds | /bot-setup"))


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    log.exception("Unhandled error in a command", exc_info=error)


async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            log.info(f"Cog loaded: {cog}")
        except Exception as e:
            log.error(f"Could not load cog '{cog}': {e}")


async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("The DISCORD_TOKEN environment variable is not set.")

    keep_alive()

    import asyncio

    asyncio.run(main())
