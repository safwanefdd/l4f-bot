# cogs/sync.py
import discord
from discord.ext import commands
from discord import app_commands
from config import GUILD_ID
from config import GUILD_ID

GUILD_OBJ = discord.Object(id=GUILD_ID) if GUILD_ID else None


class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # /resync — resynchronise sur ta guilde uniquement
    @app_commands.guilds(GUILD_OBJ)   # visibilité immédiate sur TA guilde
    @app_commands.command(name="resync", description="Resynchronise les slash commands sur la guilde.")
    @app_commands.checks.has_permissions(administrator=True)
    async def resync(self, interaction: discord.Interaction):
        if not GUILD_OBJ:
            return await interaction.response.send_message("GUILD_ID manquant côté config.", ephemeral=True)
        # on resync
        synced = await self.bot.tree.sync(guild=GUILD_OBJ)
        await interaction.response.send_message(f"✅ {len(synced)} commandes synchronisées sur la guilde.", ephemeral=True)

    # /resync_global — rare, à utiliser seulement si nécessaire
    @app_commands.command(name="resync_global", description="Synchronise globalement (lent).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    async def resync_global(self, interaction: discord.Interaction):
        synced = await self.bot.tree.sync()
        await interaction.response.send_message(f"🌍 {len(synced)} commandes globales synchronisées.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
