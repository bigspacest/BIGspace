"""
automod.py
----------
Auto-mod: detects invite links to other Discord servers, deletes the
message, and warns the user. At 3 auto-mod warnings, the user
automatically receives a warn + a 5-minute timeout (Discord's NATIVE
mute feature). A log with the reason and the original message is sent
to the channel configured via /bot-setup.
"""

import re
import discord
from discord.ext import commands

from database import get_guild_config, add_warn
from utils import make_embed, COLOR_WARN, COLOR_ERROR

INVITE_REGEX = re.compile(
    r"(discord\.gg|discord(?:app)?\.com/invite|dsc\.gg)/\S+", re.IGNORECASE
)

AUTOMOD_TIMEOUT_SECONDS = 5 * 60
WARNS_BEFORE_TIMEOUT = 3


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def message_has_invite(self, content: str) -> bool:
        return bool(INVITE_REGEX.search(content or ""))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = await get_guild_config(message.guild.id)
        if not config.get("automod_enabled", True):
            return

        if not self.message_has_invite(message.content):
            return

        member = message.author
        if member.guild_permissions.administrator:
            return

        original_content = message.content
        try:
            await message.delete()
        except discord.Forbidden:
            pass
        except discord.NotFound:
            pass

        reason = "Sending an invite link to another Discord server"
        warn_count = await add_warn(
            message.guild.id, member.id, self.bot.user.id, reason
        )

        try:
            await member.send(
                embed=make_embed(
                    title="⚠️ Automatic warning",
                    description=(
                        f"You received a warning in **{message.guild.name}**.\n"
                        f"**Reason:** {reason}\n"
                        f"**Current warnings:** {warn_count}/{WARNS_BEFORE_TIMEOUT}"
                    ),
                    color=COLOR_WARN,
                )
            )
        except discord.Forbidden:
            pass

        muted = False
        if warn_count >= WARNS_BEFORE_TIMEOUT:
            muted = await self._apply_auto_timeout(member, reason)

        await self._send_log(
            message.guild,
            config,
            member=member,
            reason=reason,
            original_content=original_content,
            channel=message.channel,
            warn_count=warn_count,
            muted=muted,
        )

    async def _apply_auto_timeout(self, member: discord.Member, reason: str) -> bool:
        try:
            until = discord.utils.utcnow() + discord.timedelta(seconds=AUTOMOD_TIMEOUT_SECONDS)
            await member.timeout(until, reason=f"Auto-mod: {reason}")
            return True
        except discord.Forbidden:
            return False

    async def _send_log(self, guild, config, *, member, reason, original_content, channel, warn_count, muted):
        log_channel_id = config.get("automod_log_channel")
        if not log_channel_id:
            return
        log_channel = guild.get_channel(log_channel_id)
        if log_channel is None:
            return

        description = (
            f"**User:** {member.mention} (`{member.id}`)\n"
            f"**Channel:** {channel.mention}\n"
            f"**Reason:** {reason}\n"
            f"**Warnings:** {warn_count}/{WARNS_BEFORE_TIMEOUT}\n"
            f"**Additional sanction:** {'5-minute automatic mute (timeout)' if muted else 'None'}\n\n"
            f"**Original message:**\n> {original_content[:1000] if original_content else '(no text content)'}"
        )

        embed = make_embed(
            title="🚨 Auto-mod: invite link detected",
            description=description,
            color=COLOR_ERROR,
        )
        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
