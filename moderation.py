"""
moderation.py
-------------
All prefix moderation commands (?lock, ?mute, ?ban, etc). main.py sets
the bot up to resolve the prefix case-insensitively, so ?lock, ?LOCK
and ?Lock all work the same way.

Muting uses Discord's NATIVE timeout feature (member.timeout()) —
not a custom "Muted" role.
"""

import discord
from discord.ext import commands

from database import (
    add_warn,
    get_warns,
    remove_warn_by_index,
    add_note,
    get_notes,
    remove_note_by_index,
)
from utils import (
    make_embed,
    success_embed,
    error_embed,
    staff_only,
    parse_duration,
    format_duration,
    MAX_TIMEOUT_SECONDS,
    COLOR_INFO,
    EMOJI_CLOCK,
    EMOJI_HOURGLASS,
    EMOJI_PEN,
    EMOJI_SEARCH,
    EMOJI_DENIED,
    EMOJI_WARNING,
    EMOJI_CHECK,
)


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------------------------------------------
    # Channel: lock / unlock / slowmode
    # -----------------------------------------------------------------

    @commands.command(name="lock")
    @staff_only()
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.reply(
            embed=success_embed(f"{channel.mention} has been locked.", title=f"{EMOJI_DENIED} Channel locked"),
            mention_author=False,
        )

    @commands.command(name="unlock")
    @staff_only()
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        await ctx.reply(
            embed=success_embed(f"{channel.mention} has been unlocked.", title=f"{EMOJI_CHECK} Channel unlocked"),
            mention_author=False,
        )

    @commands.command(name="slowmode")
    @staff_only()
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        if seconds < 0 or seconds > 21600:
            await ctx.reply(embed=error_embed("Slowmode must be between 0 and 21600 seconds."), mention_author=False)
            return
        await channel.edit(slowmode_delay=seconds)
        desc = (
            f"Slowmode for {channel.mention} set to {seconds}s."
            if seconds
            else f"Slowmode disabled in {channel.mention}."
        )
        await ctx.reply(embed=success_embed(desc, title=f"{EMOJI_CLOCK} Slowmode"), mention_author=False)

    # -----------------------------------------------------------------
    # Mute / Unmute (Discord native timeout)
    # -----------------------------------------------------------------

    @commands.command(name="mute")
    @staff_only()
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str = "10m",
        *,
        reason: str = "No reason specified",
    ):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.reply(embed=error_embed("Invalid duration. Use a format like: 10m, 2h, 1d."), mention_author=False)
            return
        if seconds > MAX_TIMEOUT_SECONDS:
            await ctx.reply(embed=error_embed("Discord timeouts can't be longer than 28 days."), mention_author=False)
            return

        try:
            await member.timeout(discord.utils.utcnow() + discord.timedelta(seconds=seconds), reason=reason)
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("I don't have permission to timeout this member."), mention_author=False)
            return

        await ctx.reply(
            embed=success_embed(
                f"{member.mention} has been muted.\n**Duration:** {format_duration(seconds)}\n**Reason:** {reason}",
                title=f"{EMOJI_HOURGLASS} Member muted",
            ),
            mention_author=False,
        )

        try:
            await member.send(
                embed=make_embed(
                    title=f"{EMOJI_HOURGLASS} You have been muted",
                    description=f"Server: **{ctx.guild.name}**\nDuration: {format_duration(seconds)}\nReason: {reason}",
                    color=COLOR_INFO,
                )
            )
        except discord.Forbidden:
            pass

    @commands.command(name="unmute")
    @staff_only()
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        if member.timed_out_until is None:
            await ctx.reply(embed=error_embed(f"{member.mention} is not muted."), mention_author=False)
            return
        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("I don't have permission to remove this member's timeout."), mention_author=False)
            return
        await ctx.reply(embed=success_embed(f"{member.mention} has been unmuted.", title=f"{EMOJI_CHECK} Member unmuted"), mention_author=False)

    # -----------------------------------------------------------------
    # Warns
    # -----------------------------------------------------------------

    @commands.command(name="warn")
    @staff_only()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason specified"):
        count = await add_warn(ctx.guild.id, member.id, ctx.author.id, reason)
        await ctx.reply(
            embed=success_embed(
                f"{member.mention} has been warned.\n**Reason:** {reason}\n**Total warnings:** {count}",
                title=f"{EMOJI_WARNING} Warning logged",
            ),
            mention_author=False,
        )
        try:
            await member.send(
                embed=make_embed(
                    title=f"{EMOJI_WARNING} You received a warning",
                    description=f"Server: **{ctx.guild.name}**\nReason: {reason}\nTotal warnings: {count}",
                    color=COLOR_INFO,
                )
            )
        except discord.Forbidden:
            pass

    @commands.command(name="delwarn")
    @staff_only()
    async def delwarn(self, ctx: commands.Context, member: discord.Member, index: int):
        ok = await remove_warn_by_index(ctx.guild.id, member.id, index)
        if ok:
            await ctx.reply(embed=success_embed(f"Warning #{index} for {member.mention} was removed."), mention_author=False)
        else:
            await ctx.reply(embed=error_embed("That warning could not be found."), mention_author=False)

    @commands.command(name="warnings")
    @staff_only()
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        warns = await get_warns(ctx.guild.id, member.id)
        if not warns:
            await ctx.reply(embed=make_embed(title=f"{EMOJI_SEARCH} Warnings", description=f"{member.mention} has no warnings."), mention_author=False)
            return
        lines = []
        for i, w in enumerate(warns, start=1):
            lines.append(f"**#{i}** — {w['reason']} (by <@{w['moderator_id']}>)")
        await ctx.reply(
            embed=make_embed(title=f"{EMOJI_SEARCH} Warnings for {member.display_name}", description="\n".join(lines), color=COLOR_INFO),
            mention_author=False,
        )

    # -----------------------------------------------------------------
    # Notes
    # -----------------------------------------------------------------

    @commands.command(name="addnote")
    @staff_only()
    async def addnote(self, ctx: commands.Context, member: discord.Member, *, content: str):
        await add_note(ctx.guild.id, member.id, ctx.author.id, content)
        await ctx.reply(embed=success_embed(f"Note added to {member.mention}."), mention_author=False)

    @commands.command(name="removenote")
    @staff_only()
    async def removenote(self, ctx: commands.Context, member: discord.Member, index: int):
        ok = await remove_note_by_index(ctx.guild.id, member.id, index)
        if ok:
            await ctx.reply(embed=success_embed(f"Note #{index} for {member.mention} was removed."), mention_author=False)
        else:
            await ctx.reply(embed=error_embed("That note could not be found."), mention_author=False)

    @commands.command(name="viewnotes")
    @staff_only()
    async def viewnotes(self, ctx: commands.Context, member: discord.Member):
        notes = await get_notes(ctx.guild.id, member.id)
        if not notes:
            await ctx.reply(embed=make_embed(title=f"{EMOJI_PEN} Notes", description=f"{member.mention} has no notes."), mention_author=False)
            return
        lines = [f"**#{i}** — {n['content']} (by <@{n['moderator_id']}>)" for i, n in enumerate(notes, start=1)]
        await ctx.reply(
            embed=make_embed(title=f"{EMOJI_PEN} Notes for {member.display_name}", description="\n".join(lines), color=COLOR_INFO),
            mention_author=False,
        )

    # -----------------------------------------------------------------
    # Ban / Tempban / Unban
    # -----------------------------------------------------------------

    @commands.command(name="ban")
    @staff_only()
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason specified"):
        try:
            await member.send(
                embed=make_embed(title=f"{EMOJI_DENIED} You have been banned", description=f"Server: **{ctx.guild.name}**\nReason: {reason}", color=COLOR_INFO)
            )
        except discord.Forbidden:
            pass
        await ctx.guild.ban(member, reason=f"{reason} | Sanctioned by {ctx.author}")
        await ctx.reply(embed=success_embed(f"{member.mention} has been banned.\n**Reason:** {reason}", title=f"{EMOJI_DENIED} Member banned"), mention_author=False)

    @commands.command(name="tempban")
    @staff_only()
    async def tempban(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "No reason specified"):
        seconds = parse_duration(duration)
        if seconds is None:
            await ctx.reply(embed=error_embed("Invalid duration. Use a format like: 10m, 2h, 1d."), mention_author=False)
            return

        user_id = member.id
        try:
            await member.send(
                embed=make_embed(
                    title=f"{EMOJI_HOURGLASS} You have been temporarily banned",
                    description=f"Server: **{ctx.guild.name}**\nDuration: {format_duration(seconds)}\nReason: {reason}",
                    color=COLOR_INFO,
                )
            )
        except discord.Forbidden:
            pass

        await ctx.guild.ban(member, reason=f"Tempban: {reason} | Sanctioned by {ctx.author}")
        await ctx.reply(
            embed=success_embed(
                f"{member.mention} has been banned for {format_duration(seconds)}.\n**Reason:** {reason}",
                title=f"{EMOJI_HOURGLASS} Temporary ban applied",
            ),
            mention_author=False,
        )

        import asyncio

        async def unban_later():
            await asyncio.sleep(seconds)
            try:
                await ctx.guild.unban(discord.Object(id=user_id), reason="Tempban duration expired")
            except discord.NotFound:
                pass
            except discord.Forbidden:
                pass

        self.bot.loop.create_task(unban_later())

    @commands.command(name="unban")
    @staff_only()
    async def unban(self, ctx: commands.Context, user_id: int):
        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=f"Unbanned by {ctx.author}")
            await ctx.reply(embed=success_embed(f"User with ID `{user_id}` has been unbanned."), mention_author=False)
        except discord.NotFound:
            await ctx.reply(embed=error_embed("That user is not banned."), mention_author=False)

    # -----------------------------------------------------------------
    # Clear / Userinfo / DM / Cmds
    # -----------------------------------------------------------------

    @commands.command(name="clear")
    @staff_only()
    async def clear(self, ctx: commands.Context, amount: int):
        if amount < 1 or amount > 100:
            await ctx.reply(embed=error_embed("Amount must be between 1 and 100."), mention_author=False)
            return
        deleted = await ctx.channel.purge(limit=amount + 1)
        msg = await ctx.send(embed=success_embed(f"Deleted {len(deleted) - 1} messages.", title=f"{EMOJI_CHECK} Chat cleared"))
        import asyncio

        await asyncio.sleep(4)
        try:
            await msg.delete()
        except discord.NotFound:
            pass

    @commands.command(name="userinfo")
    @staff_only()
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        roles = ", ".join(r.mention for r in member.roles if r != ctx.guild.default_role) or "None"
        embed = make_embed(
            title=f"{EMOJI_SEARCH} Info for {member.display_name}",
            color=COLOR_INFO,
            description=(
                f"**User:** {member.mention} (`{member.id}`)\n"
                f"**Account created:** {discord.utils.format_dt(member.created_at, style='F')}\n"
                f"**Joined server:** {discord.utils.format_dt(member.joined_at, style='F')}\n"
                f"**Roles:** {roles}"
            ),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="dm")
    @staff_only()
    async def dm(self, ctx: commands.Context, member: discord.Member, *, message: str):
        try:
            await member.send(
                embed=make_embed(
                    title=f"{EMOJI_PEN} Message from {ctx.guild.name}",
                    description=message,
                    color=COLOR_INFO,
                )
            )
            await ctx.reply(embed=success_embed(f"Message sent to {member.mention}."), mention_author=False)
        except discord.Forbidden:
            await ctx.reply(embed=error_embed("I couldn't DM that user."), mention_author=False)

    @commands.command(name="cmds")
    async def cmds(self, ctx: commands.Context):
        prefix = ctx.prefix
        embed = make_embed(
            title=f"{EMOJI_SEARCH} Available Commands",
            description=f"Here's everything you can do with `{prefix}` commands.\u200b\n\u200b",
            color=COLOR_INFO,
        )
        embed.add_field(
            name=f"{EMOJI_DENIED} Channel",
            value=f"`{prefix}lock`\n`{prefix}unlock`\n`{prefix}slowmode`",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI_HOURGLASS} Mute",
            value=f"`{prefix}mute`\n`{prefix}unmute`",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI_WARNING} Warnings",
            value=f"`{prefix}warn`\n`{prefix}delwarn`\n`{prefix}warnings`",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI_PEN} Notes",
            value=f"`{prefix}addnote`\n`{prefix}removenote`\n`{prefix}viewnotes`",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI_DENIED} Bans",
            value=f"`{prefix}ban`\n`{prefix}tempban`\n`{prefix}unban`",
            inline=True,
        )
        embed.add_field(
            name=f"{EMOJI_SEARCH} Utility",
            value=f"`{prefix}clear`\n`{prefix}userinfo`\n`{prefix}dm`",
            inline=True,
        )
        embed.set_footer(text="\u200b")
        await ctx.reply(embed=embed, mention_author=False)

    # -----------------------------------------------------------------
    # Common error handling for these commands
    # -----------------------------------------------------------------

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MemberNotFound):
            await ctx.reply(embed=error_embed("I couldn't find that member."), mention_author=False)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(embed=error_embed(f"Missing argument: `{error.param.name}`."), mention_author=False)
        elif isinstance(error, commands.BadArgument):
            await ctx.reply(embed=error_embed("One of the arguments provided is invalid."), mention_author=False)
        elif isinstance(error, commands.CheckFailure):
            pass  # already reported inside the check (staff_only)
        elif isinstance(error, discord.Forbidden):
            await ctx.reply(embed=error_embed("I don't have enough permissions to do that."), mention_author=False)
        else:
            await ctx.reply(embed=error_embed(f"An unexpected error occurred: `{error}`"), mention_author=False)
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
