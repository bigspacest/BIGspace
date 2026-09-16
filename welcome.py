"""
welcome.py
----------
Configurable welcome system via an interactive panel.

Command: /welcome-setup
Running it sends a panel (embed + buttons/selects) where you can
configure: channel, color, ping the user, image/gif, footer, links
(buttons that redirect somewhere), format (embed or plain text), and
recommended channels mentioned to the new member.
"""

import discord
from discord import app_commands
from discord.ext import commands

from database import get_welcome_config, update_welcome_config
from utils import (
    make_embed,
    error_embed,
    replace_placeholders,
    COLOR_NEUTRAL,
)


def build_preview_embed(config: dict, member: discord.Member, guild: discord.Guild) -> discord.Embed:
    title = replace_placeholders(config.get("title") or "", member=member, guild=guild)
    description = replace_placeholders(config.get("description") or "", member=member, guild=guild)
    embed = discord.Embed(
        title=title or None,
        description=description or None,
        color=config.get("embed_color", COLOR_NEUTRAL),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    if config.get("image_url"):
        embed.set_image(url=config["image_url"])
    if config.get("footer_text"):
        embed.set_footer(text=replace_placeholders(config["footer_text"], member=member, guild=guild))
    return embed


def build_links_view(config: dict) -> discord.ui.View | None:
    links = config.get("links") or []
    if not links:
        return None
    view = discord.ui.View(timeout=None)
    for link in links[:25]:
        label = link.get("label", "Link")[:80]
        url = link.get("url")
        if url:
            view.add_item(discord.ui.Button(label=label, url=url, style=discord.ButtonStyle.link))
    return view


# ---------------------------------------------------------------------------
# Modals
# ---------------------------------------------------------------------------

class ColorModal(discord.ui.Modal, title="Embed color"):
    color_input = discord.ui.TextInput(
        label="Color in HEX (e.g. #5865F2)",
        placeholder="#5865F2",
        max_length=7,
        required=True,
    )

    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.color_input.value.strip().lstrip("#")
        try:
            value = int(raw, 16)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("That is not a valid HEX color."), ephemeral=True
            )
            return
        self.parent_view.config["embed_color"] = value
        await update_welcome_config(self.parent_view.guild_id, {"embed_color": value})
        await self.parent_view.refresh(interaction)


class ImageModal(discord.ui.Modal, title="Welcome image or GIF"):
    url_input = discord.ui.TextInput(
        label="Image or GIF URL (empty = remove)",
        placeholder="https://...",
        required=False,
        max_length=500,
    )

    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        value = self.url_input.value.strip() or None
        self.parent_view.config["image_url"] = value
        await update_welcome_config(self.parent_view.guild_id, {"image_url": value})
        await self.parent_view.refresh(interaction)


class TextModal(discord.ui.Modal, title="Welcome text"):
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="Welcome, {user}!",
        required=False,
        max_length=256,
    )
    description_input = discord.ui.TextInput(
        label="Description",
        placeholder="You can use {user} {username} {server} {member_count}",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=2000,
    )

    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__()
        self.title_input.default = parent_view.config.get("title", "")
        self.description_input.default = parent_view.config.get("description", "")
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        title = self.title_input.value.strip()
        description = self.description_input.value.strip()
        self.parent_view.config["title"] = title
        self.parent_view.config["description"] = description
        await update_welcome_config(
            self.parent_view.guild_id, {"title": title, "description": description}
        )
        await self.parent_view.refresh(interaction)


class FooterModal(discord.ui.Modal, title="Embed footer"):
    footer_input = discord.ui.TextInput(
        label="Footer text (empty = remove)",
        required=False,
        max_length=200,
    )

    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__()
        self.footer_input.default = parent_view.config.get("footer_text", "") or ""
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        value = self.footer_input.value.strip() or None
        self.parent_view.config["footer_text"] = value
        await update_welcome_config(self.parent_view.guild_id, {"footer_text": value})
        await self.parent_view.refresh(interaction)


class LinkModal(discord.ui.Modal, title="Add link"):
    label_input = discord.ui.TextInput(label="Button name", max_length=80, required=True)
    url_input = discord.ui.TextInput(label="URL", placeholder="https://...", max_length=300, required=True)

    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip()
        if not url.startswith(("http://", "https://")):
            await interaction.response.send_message(
                embed=error_embed("The URL must start with http:// or https://"), ephemeral=True
            )
            return
        links = self.parent_view.config.get("links", [])
        if len(links) >= 5:
            await interaction.response.send_message(
                embed=error_embed("Maximum of 5 links."), ephemeral=True
            )
            return
        links.append({"label": self.label_input.value.strip(), "url": url})
        self.parent_view.config["links"] = links
        await update_welcome_config(self.parent_view.guild_id, {"links": links})
        await self.parent_view.refresh(interaction)


# ---------------------------------------------------------------------------
# Selects
# ---------------------------------------------------------------------------

class WelcomeChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__(
            placeholder="📌 Welcome channel",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        channel = self.values[0]
        self.parent_view.config["channel_id"] = channel.id
        self.parent_view.config["enabled"] = True
        await update_welcome_config(
            self.parent_view.guild_id, {"channel_id": channel.id, "enabled": True}
        )
        await self.parent_view.refresh(interaction)


class RecommendedChannelsSelect(discord.ui.ChannelSelect):
    def __init__(self, parent_view: "WelcomeSetupView"):
        super().__init__(
            placeholder="⭐ Recommended channels (mentioned to the new member)",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=5,
            row=1,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        ids = [c.id for c in self.values]
        self.parent_view.config["recommended_channels"] = ids
        await update_welcome_config(self.parent_view.guild_id, {"recommended_channels": ids})
        await self.parent_view.refresh(interaction)


# ---------------------------------------------------------------------------
# Main panel view
# ---------------------------------------------------------------------------

class WelcomeSetupView(discord.ui.View):
    def __init__(self, guild_id: int, config: dict, invoker_id: int):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.config = config
        self.invoker_id = invoker_id

        self.add_item(WelcomeChannelSelect(self))
        self.add_item(RecommendedChannelsSelect(self))

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
        status = "🟢 Enabled" if c.get("enabled") else "🔴 Disabled"
        channel = f"<#{c['channel_id']}>" if c.get("channel_id") else "Not configured"
        color_hex = f"#{c.get('embed_color', 0):06X}"
        format_ = "Embed" if c.get("use_embed", True) else "Plain text"
        ping = "Yes" if c.get("ping_user", True) else "No"
        recommended = c.get("recommended_channels") or []
        recommended_str = ", ".join(f"<#{cid}>" for cid in recommended) if recommended else "None"
        links = c.get("links") or []
        links_str = ", ".join(l["label"] for l in links) if links else "None"

        embed = make_embed(
            title="⚙️ Welcome System Configuration",
            description=(
                f"**Status:** {status}\n"
                f"**Channel:** {channel}\n"
                f"**Format:** {format_}\n"
                f"**Ping user:** {ping}\n"
                f"**Color:** {color_hex}\n"
                f"**Image/GIF:** {'Set' if c.get('image_url') else 'None'}\n"
                f"**Footer:** {c.get('footer_text') or 'None'}\n"
                f"**Links:** {links_str}\n"
                f"**Recommended channels:** {recommended_str}\n\n"
                f"Use the buttons and menus below to configure each option."
            ),
            color=c.get("embed_color", COLOR_NEUTRAL),
        )
        return embed

    async def refresh(self, interaction: discord.Interaction):
        embed = self.build_panel_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    # --- Row 2: content buttons ---

    @discord.ui.button(label="Color", emoji="🎨", style=discord.ButtonStyle.secondary, row=2)
    async def color_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ColorModal(self))

    @discord.ui.button(label="Text (title/desc.)", emoji="📝", style=discord.ButtonStyle.secondary, row=2)
    async def text_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TextModal(self))

    @discord.ui.button(label="Image/GIF", emoji="🖼️", style=discord.ButtonStyle.secondary, row=2)
    async def image_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ImageModal(self))

    @discord.ui.button(label="Footer", emoji="🔖", style=discord.ButtonStyle.secondary, row=2)
    async def footer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FooterModal(self))

    @discord.ui.button(label="Add link", emoji="🔗", style=discord.ButtonStyle.secondary, row=3)
    async def link_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LinkModal(self))

    @discord.ui.button(label="Clear links", emoji="🗑️", style=discord.ButtonStyle.secondary, row=3)
    async def clear_links_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.config["links"] = []
        await update_welcome_config(self.guild_id, {"links": []})
        await self.refresh(interaction)

    # --- Row 4: toggles ---

    @discord.ui.button(label="Ping: on/off", emoji="🔔", style=discord.ButtonStyle.primary, row=4)
    async def ping_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_value = not self.config.get("ping_user", True)
        self.config["ping_user"] = new_value
        await update_welcome_config(self.guild_id, {"ping_user": new_value})
        await self.refresh(interaction)

    @discord.ui.button(label="Format: Embed/Text", emoji="🔁", style=discord.ButtonStyle.primary, row=4)
    async def format_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_value = not self.config.get("use_embed", True)
        self.config["use_embed"] = new_value
        await update_welcome_config(self.guild_id, {"use_embed": new_value})
        await self.refresh(interaction)

    @discord.ui.button(label="Enable/Disable", emoji="⚡", style=discord.ButtonStyle.success, row=4)
    async def enabled_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_value = not self.config.get("enabled", False)
        self.config["enabled"] = new_value
        await update_welcome_config(self.guild_id, {"enabled": new_value})
        await self.refresh(interaction)


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="welcome-setup", description="Configure the server's welcome system")
    @app_commands.checks.has_permissions(administrator=True)
    async def welcome_setup(self, interaction: discord.Interaction):
        config = await get_welcome_config(interaction.guild_id)
        view = WelcomeSetupView(interaction.guild_id, config, interaction.user.id)
        await interaction.response.send_message(embed=view.build_panel_embed(), view=view, ephemeral=True)

    @welcome_setup.error
    async def welcome_setup_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                embed=error_embed("You need administrator permissions to use this command."),
                ephemeral=True,
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await get_welcome_config(member.guild.id)
        if not config.get("enabled") or not config.get("channel_id"):
            return
        channel = member.guild.get_channel(config["channel_id"])
        if channel is None:
            return

        content = member.mention if config.get("ping_user", True) else None
        recommended = config.get("recommended_channels") or []
        rec_mentions = " ".join(f"<#{cid}>" for cid in recommended)

        view = build_links_view(config)

        try:
            if config.get("use_embed", True):
                embed = build_preview_embed(config, member, member.guild)
                if rec_mentions:
                    embed.add_field(name="You might want to check out", value=rec_mentions, inline=False)
                await channel.send(content=content, embed=embed, view=view)
            else:
                text = replace_placeholders(
                    config.get("description") or "Welcome, {user}!",
                    member=member,
                    guild=member.guild,
                )
                if rec_mentions:
                    text += f"\n\nYou might want to check out: {rec_mentions}"
                full = f"{content}\n{text}" if content else text
                await channel.send(content=full, view=view)
        except discord.Forbidden:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
