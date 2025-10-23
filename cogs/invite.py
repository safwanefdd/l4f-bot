# -*- coding: utf-8 -*-
# cogs/invite.py
import discord
from discord.ext import commands
from discord import app_commands
from config import GUILD_ID

GUILD_OBJ = discord.Object(id=GUILD_ID) if GUILD_ID else None
INVITE_MAX_AGE = 60 * 60
INVITE_MAX_USES = 1


class Invite(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(GUILD_OBJ)
    @app_commands.command(
        name="invite",
        description="Invite un utilisateur en MP vers TON salon vocal actuel."
    )
    @app_commands.describe(user="La personne à inviter (MP)")
    async def invite(self, interaction: discord.Interaction, user: discord.User):  # <<< ASYNC
        member = interaction.user
        vs = getattr(member, "voice", None)
        if not vs or not vs.channel:
            return await interaction.response.send_message(
                "❌ Tu dois être connecté·e à un salon vocal.", ephemeral=True
            )

        channel = vs.channel
        guild = interaction.guild
        me = guild.me if guild else None
        perms = channel.permissions_for(me) if me else None
        if not perms or not perms.create_instant_invite:
            return await interaction.response.send_message(
                "⚠️ Il me manque la permission **Créer une invitation** sur ce salon.",
                ephemeral=True
            )

        try:
            invite = await channel.create_invite(
                max_age=INVITE_MAX_AGE, max_uses=INVITE_MAX_USES, unique=True,
                reason=f"Invitation demandée par {member} pour {user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "⚠️ Impossible de créer une invitation pour ce salon.", ephemeral=True
            )

        try:
            await user.send(
                f"🎧 **{member.display_name}** t’invite à rejoindre **{channel.name}** "
                f"sur **{guild.name}**.\n👉 {invite.url}\n"
                f"_(valable {INVITE_MAX_AGE//3600}h, {INVITE_MAX_USES} utilisation)_"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"❌ Je ne peux pas DM {user.mention}.", ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ Invitation envoyée à {user.mention} en **MP**.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Invite(bot))
