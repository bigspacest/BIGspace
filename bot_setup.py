"""
bot_setup.py
------------
General bot configuration panel.

Command: /bot-setup
Lets you configure: staff roles, admin roles, and the auto-mod log
channel.
"""

import discord
from discord import app_commands
from discord.ext import commands

from database import get_guild_config, update_guild_config
from utils import make_embed, error_embed, COLOR_NEUTRAL


class StaffRolesSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view: "BotSetupView"):
        super().__init__(
            placeholder="👮 Staff roles (moderators)",
            min_values=0,
            max_values=10,
            row=0,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        ids = [r.id for r in self.values]
        self.parent_view.config["staff_roles"] = ids
        await update_guild_config(self.parent_view.guild_id, {"staff_roles": ids})
        await self.parent_view.refresh(interaction)


class AdminRolesSelect(discord.ui.RoleSelect):
    def __init__(self, parent_view: "BotSetupView"):
        super().__init__(
            placeholder="🛡️ Administrator roles",
            min_values=0,
            max_values=10,
            row=1,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        ids = [r.id for r in self.values]
        self.parent_view.config["admin_roles"] = ids
        await update_guild_config(self.parent_view.guild_id, {"admin_roles": ids})
        await self.parent_view.refresh(interaction)


class AutomodLogChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: "BotSetupView"):
        super().__init__(
            placeholder="📋 Auto-mod log channel",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=2,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.values[0].id if self.values else None
        self.parent_view.config["automod_log_channel"] = channel_id
        await update_guild_config(self.parent_view.guild_id, {"automod_log_channel": channel_id})
        await self.parent_view.refresh(interaction)


class BotSetupView(discord.ui.View):
    def __init__(self, guild_id: int, config: dict, invoker_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.config = config
        self.invoker_id = invoker_id

        self.add_item(StaffRolesSelect(self))
        self.add_item(AdminRolesSelect(self))
        self.add_item(AutomodLogChannelSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message(
                embed=error_embed("Only the person who ran this command can use this panel."),
                ephemeral=True,
            )
            return False
        return True

    def build_panel_embed(self) -> discord.Embed:
        c = self.config
        staff = ", ".join(f"<@&{rid}>" for rid in c.get("staff_roles", [])) or "None"
        admin = ", ".join(f"<@&{rid}>" for rid in c.get("admin_roles", [])) or "None"
        log_channel = f"<#{c['automod_log_channel']}>" if c.get("automod_log_channel") else "Not configured"
        automod_status = "🟢 Enabled" if c.get("automod_enabled", True) else "🔴 Disabled"

        return make_embed(
            title="⚙️ General Bot Configuration",
            description=(
                f"**Staff roles:** {staff}\n"
                f"**Administrator roles:** {admin}\n"
                f"**Auto-mod log channel:** {log_channel}\n"
                f"**Auto-mod:** {automod_status}\n\n"
                f"Use the menus and buttons below to configure each option."
            ),
            color=COLOR_NEUTRAL,
        )

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_panel_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Auto-mod: on/off", emoji="🛡️", style=discord.ButtonStyle.primary, row=3)
    async def automod_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_value = not self.config.get("automod_enabled", True)
        self.config["automod_enabled"] = new_value
        await update_guild_config(self.guild_id, {"automod_enabled": new_value})
        await self.refresh(interaction)


class BotSetup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="bot-setup", description="Configure the bot's general settings")
    @app_commands.checks.has_permissions(administrator=True)
    async def bot_setup(self, interaction: discord.Interaction):
        config = await get_guild_config(interaction.guild_id)
        view = BotSetupView(interaction.guild_id, config, interaction.user.id)
        await interaction.response.send_message(embed=view.build_panel_embed(), view=view, ephemeral=True)

    @bot_setup.error
    async def bot_setup_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("You need administrator permissions to use this command."),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(BotSetup(bot))
