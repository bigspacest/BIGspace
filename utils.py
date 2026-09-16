"""
utils.py
--------
Shared utility functions used across the bot: standardized embeds,
permission checks (staff/admin based on bot-setup), and duration parsing
("5m", "1h", "2d") for timeouts and temp bans.

Note: muting is done through Discord's NATIVE timeout feature
(member.timeout()), not a custom "Muted" role.
"""

import re
import discord
from discord.ext import commands

from database import get_guild_config

COLOR_SUCCESS = 0x57F287
COLOR_ERROR = 0xED4245
COLOR_WARN = 0xFEE75C
COLOR_INFO = 0x5865F2
COLOR_NEUTRAL = 0x2B2D31

# Discord's max timeout duration is 28 days
MAX_TIMEOUT_SECONDS = 28 * 24 * 3600

_DURATION_RE = re.compile(r"^(\d+)([smhd])$", re.IGNORECASE)
_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text: str):
    """Converts '10m', '2h', '1d', '30s' into seconds. Returns None if invalid."""
    if not text:
        return None
    match = _DURATION_RE.match(text.strip())
    if not match:
        return None
    amount, unit = match.groups()
    return int(amount) * _DURATION_UNITS[unit.lower()]


def format_duration(seconds: int) -> str:
    if seconds is None:
        return "Permanent"
    units = [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    parts = []
    remaining = int(seconds)
    for label, size in units:
        if remaining >= size:
            value, remaining = divmod(remaining, size)
            parts.append(f"{value}{label}")
    return " ".join(parts) if parts else "0s"


def make_embed(
    *,
    title: str = None,
    description: str = None,
    color: int = COLOR_INFO,
    footer: str = None,
    author: discord.abc.User = None,
) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    if footer:
        embed.set_footer(text=footer)
    if author:
        embed.set_author(name=str(author), icon_url=author.display_avatar.url)
    return embed


def success_embed(description: str, title: str = "✅ Done") -> discord.Embed:
    return make_embed(title=title, description=description, color=COLOR_SUCCESS)


def error_embed(description: str, title: str = "❌ Error") -> discord.Embed:
    return make_embed(title=title, description=description, color=COLOR_ERROR)


# ---------------------------------------------------------------------------
# Permissions: staff / admin as configured in /bot-setup
# ---------------------------------------------------------------------------

async def is_staff(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    config = await get_guild_config(member.guild.id)
    staff_roles = set(config.get("staff_roles", []))
    admin_roles = set(config.get("admin_roles", []))
    member_role_ids = {r.id for r in member.roles}
    return bool(member_role_ids & (staff_roles | admin_roles))


async def is_admin(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    config = await get_guild_config(member.guild.id)
    admin_roles = set(config.get("admin_roles", []))
    member_role_ids = {r.id for r in member.roles}
    return bool(member_role_ids & admin_roles)


def staff_only():
    """Decorator for commands that require a staff role (or administrator)."""

    async def predicate(ctx: commands.Context):
        if not ctx.guild:
            return False
        if not await is_staff(ctx.author):
            await ctx.reply(
                embed=error_embed("You don't have permission to use this command."),
                mention_author=False,
            )
            return False
        return True

    return commands.check(predicate)


def admin_only():
    """Decorator for commands that require an administrator role."""

    async def predicate(ctx: commands.Context):
        if not ctx.guild:
            return False
        if not await is_admin(ctx.author):
            await ctx.reply(
                embed=error_embed("You need administrator permissions for this."),
                mention_author=False,
            )
            return False
        return True

    return commands.check(predicate)


def replace_placeholders(text: str, *, member: discord.Member, guild: discord.Guild) -> str:
    if not text:
        return text
    return (
        text.replace("{user}", member.mention)
        .replace("{username}", member.display_name)
        .replace("{server}", guild.name)
        .replace("{member_count}", str(guild.member_count))
    )
