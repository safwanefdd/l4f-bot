# cogs/panel.py
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional
from cogs.voice_manager import owner_to_voice
from cogs.utils import control_embed
from config import GUILD_ID


class RenameModal(discord.ui.Modal, title="Renommer le salon"):
    """Fenêtre de renommage du salon (modale Discord)."""
    new_name = discord.ui.TextInput(
        label="Nouveau nom", placeholder="🎮 Salon de Nathalie", max_length=96)

    def __init__(self, channel_id: int, owner_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Tu n'es pas propriétaire de ce salon.", ephemeral=True)
            return

        ch = interaction.guild.get_channel(self.channel_id)
        if isinstance(ch, discord.VoiceChannel):
            try:
                await ch.edit(name=str(self.new_name))
                await interaction.response.send_message(f"✅ Salon renommé en **{self.new_name}**", ephemeral=True)
            except Exception:
                await interaction.response.send_message("⚠️ Impossible de renommer ce salon.", ephemeral=True)


class VCPanel(discord.ui.View):
    """Vue contenant les boutons du panneau de contrôle."""

    def __init__(self, owner_id: int, channel_id: int):
        super().__init__(timeout=None)  # timeout=None => persistant
        self.owner_id = owner_id
        self.channel_id = channel_id

    async def get_channel(self, interaction: discord.Interaction) -> Optional[discord.VoiceChannel]:
        ch = interaction.guild.get_channel(self.channel_id)
        return ch if isinstance(ch, discord.VoiceChannel) else None

    async def ensure_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Seul·e le/la propriétaire peut faire ça.", ephemeral=True)
            return False
        return True

    # === BOUTONS ===
    @discord.ui.button(label="🔒 Verrouiller", style=discord.ButtonStyle.secondary, custom_id="vc:lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        ch = await self.get_channel(interaction)
        if ch:
            await ch.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("🔒 Salon verrouillé (invitation obligatoire).", ephemeral=True)

    @discord.ui.button(label="🔓 Déverrouiller", style=discord.ButtonStyle.secondary, custom_id="vc:unlock")
    async def unlock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        ch = await self.get_channel(interaction)
        if ch:
            await ch.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("🔓 Salon déverrouillé.", ephemeral=True)

    @discord.ui.button(label="➕ Slots", style=discord.ButtonStyle.primary, custom_id="vc:addslot")
    async def add_slot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        ch = await self.get_channel(interaction)
        if ch:
            limit = ch.user_limit or len(ch.members)
            new = min(99, max(limit, len(ch.members)) + 1)
            await ch.edit(user_limit=new if new > 0 else 0)
            await interaction.response.send_message(f"👥 Limite passée à **{new}**", ephemeral=True)

    @discord.ui.button(label="➖ Slots", style=discord.ButtonStyle.primary, custom_id="vc:subslot")
    async def sub_slot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        ch = await self.get_channel(interaction)
        if ch:
            limit = ch.user_limit or len(ch.members)
            new = max(len(ch.members), limit - 1)
            await ch.edit(user_limit=new if new > 0 else 0)
            await interaction.response.send_message(f"👥 Limite passée à **{new}**", ephemeral=True)

    @discord.ui.button(label="✏️ Renommer", style=discord.ButtonStyle.success, custom_id="vc:rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.ensure_owner(interaction):
            return
        await interaction.response.send_modal(RenameModal(self.channel_id, self.owner_id))


class Panel(commands.Cog):
    """Commande slash /panel pour gérer son salon vocal."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="panel", description="Ouvre ton panneau de contrôle vocal")
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.command(name="panel", description="Ouvre ton panneau de contrôle vocal")
    async def panel(self, interaction: discord.Interaction):
        owner_ch_id = owner_to_voice.get(interaction.user.id)
        if not owner_ch_id:
            await interaction.response.send_message("❌ Tu n’as pas de salon perso actif.", ephemeral=True)
            return

        ch = interaction.guild.get_channel(owner_ch_id)
        if not isinstance(ch, discord.VoiceChannel):
            await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)
            return

        await interaction.response.send_message(
            embed=control_embed(interaction.user, ch),
            view=VCPanel(interaction.user.id, ch.id),
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Panel(bot))
