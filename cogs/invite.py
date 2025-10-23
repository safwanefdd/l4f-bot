# cogs/invite.py
import discord
from discord.ext import commands
from discord import app_commands

INVITE_MAX_AGE = 60 * 60       # 1 heure
INVITE_MAX_USES = 1            # une seule utilisation


class Invite(commands.Cog):
    """Slash /invite : envoie en MP une invitation vers TON salon vocal actuel."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="invite",
        description="Invite quelqu’un en MP à rejoindre ton salon vocal actuel."
    )
    @app_commands.describe(user="Utilisateur à inviter (reçoit un MP avec le lien)")
    async def invite(self, interaction: discord.Interaction, user: discord.User):
        member = interaction.user
        voice_state = getattr(member, "voice", None)
        if not voice_state or not voice_state.channel:
            return await interaction.response.send_message(
                "❌ Tu dois être connecté·e à un **salon vocal** pour utiliser cette commande.",
                ephemeral=True
            )

        voice_channel = voice_state.channel
        guild = interaction.guild
        assert guild is not None

        me = guild.me
        perms = voice_channel.permissions_for(me) if me else None
        if not perms or not perms.create_instant_invite:
            return await interaction.response.send_message(
                "⚠️ Il me manque la permission **Créer une invitation** sur ce salon.",
                ephemeral=True
            )

        try:
            invite = await voice_channel.create_invite(
                max_age=INVITE_MAX_AGE,
                max_uses=INVITE_MAX_USES,
                unique=True,
                reason=f"Invitation demandée par {member} pour {user}"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "⚠️ Je n’ai pas la permission de créer une invitation pour ce salon.",
                ephemeral=True
            )
        except Exception as e:
            return await interaction.response.send_message(
                f"⚠️ Erreur lors de la création de l’invitation : {e}",
                ephemeral=True
            )

        try:
            await user.send(
                f"🎧 **{member.display_name}** t’invite à rejoindre le salon vocal "
                f"**{voice_channel.name}** sur **{guild.name}**.\n"
                f"👉 Lien d’invitation : {invite.url}\n"
                f"*(valable {INVITE_MAX_AGE//3600}h, {INVITE_MAX_USES} utilisation)*"
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"❌ Impossible d’envoyer un message privé à {user.mention}.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"✅ Invitation envoyée à {user.mention} en **MP**.",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Invite(bot))
