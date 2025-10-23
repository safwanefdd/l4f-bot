from discord.ext import commands
import discord
from config import WELCOME_CHANNEL_ID, WELCOME_ROLE_ID, SEND_WELCOME_DM


class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Rôle auto
        if WELCOME_ROLE_ID:
            role = member.guild.get_role(WELCOME_ROLE_ID)
            if role:
                await member.add_roles(role, reason="Bienvenue")

        # Embed public
        if WELCOME_CHANNEL_ID:
            ch = member.guild.get_channel(WELCOME_CHANNEL_ID)
            if ch:
                embed = discord.Embed(
                    title=f"👋 Bienvenue {member.display_name} !",
                    description="Ravi·e de t’avoir parmi nous 🎮",
                    colour=discord.Colour.green()
                )
                embed.set_thumbnail(url=member.display_avatar)
                await ch.send(embed=embed)

        # DM perso
        if SEND_WELCOME_DM:
            try:
                await member.send("Bienvenue sur le serveur ! N'hésites pas à poser tes questions, nous sommes à l'écoute 🎧")
            except:
                pass


async def setup(bot):
    await bot.add_cog(Welcome(bot))
