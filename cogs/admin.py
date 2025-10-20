from discord.ext import commands
from discord import app_commands
import discord

class Admin(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="sync", description="Resynchroniser les slash commands (admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.client.tree.sync(guild=interaction.guild)
            await interaction.followup.send("✅ Slash commands resynchronisées (guild).", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ Erreur: {e}", ephemeral=True)

async def setup(bot): await bot.add_cog(Admin(bot))
