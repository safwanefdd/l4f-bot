# cogs/sync.py
import discord
from discord.ext import commands
from discord import app_commands
from config import GUILD_ID


class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sync", description="Resynchronise les slash commands sur la guilde.")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        if not GUILD_ID:
            await interaction.response.send_message("GUILD_ID manquant côté config.", ephemeral=True)
            return
        guild = discord.Object(id=GUILD_ID)
        # On nettoie d’abord les commandes guild, puis on re-sync
        self.bot.tree.clear_commands(guild=guild)
        synced = await self.bot.tree.sync(guild=guild)
        await interaction.response.send_message(f"✅ {len(synced)} commandes synchronisées sur la guilde.", ephemeral=True)

    @app_commands.command(name="sync-global", description="(rare) Sync global (peut prendre du temps).")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_global(self, interaction: discord.Interaction):
        synced = await self.bot.tree.sync()
        await interaction.response.send_message(f"🌍 {len(synced)} commandes synchronisées globalement.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
