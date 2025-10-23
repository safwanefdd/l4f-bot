# -*- coding: utf-8 -*-
# cogs/moderation.py
import os
import time
import uuid
import typing as t
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from config import GUILD_ID
from config import SIGNALEMENT_CHANNEL_ID

GUILD_OBJ = discord.Object(id=GUILD_ID) if GUILD_ID else None
SIGNALEMENT_CHANNEL_ID = SIGNALEMENT_CHANNEL_ID if SIGNALEMENT_CHANNEL_ID else 0

APPEAL_WINDOW_SECONDS = 10 * 60
APPEAL_MAX_ATTACHMENTS = 5
APPEAL_MAX_FORWARD_BYTES = 25 * 1024**2

ACTIVE_APPEALS: dict[int, tuple[str, float]] = {}


def _now() -> float:
    return time.time()


class AppealView(discord.ui.View):
    def __init__(self, token: str):
        super().__init__(timeout=None)
        self.token = token

    @discord.ui.button(label="Contester mon bannissement", style=discord.ButtonStyle.primary)
    async def appeal_open(self, interaction: discord.Interaction, _: discord.ui.Button):
        # 1) Toujours ACCUSER RÉCEPTION rapidement (en DM pas d'éphémère)
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()  # OK en DM, évite "échec de l'interaction"
        except Exception:
            pass

        # 2) Ouvrir la fenêtre de contestation
        ACTIVE_APPEALS[interaction.user.id] = (
            self.token, _now() + APPEAL_WINDOW_SECONDS)

        # 3) Donner les consignes dans le même DM (pas d'ephemeral en MP)
        text = (
            f"📝 **Contestation ouverte !**\n\n"
            f"Explique calmement ta situation et joins, si besoin, **audio/vidéo/images**.\n"
            f"Tu as **{APPEAL_WINDOW_SECONDS//60} minutes**.\n\n"
            f"➡️ Envoie **un seul message** ici avec ton explication et tes pièces jointes."
        )
        # Priorité: followup dans le même fil DM; sinon fallback en user.send()
        try:
            await interaction.followup.send(text)
        except Exception:
            try:
                await interaction.user.send(text)
            except Exception:
                # rien de plus à faire : l'utilisateur a fermé ses MP
                pass


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._gc_task = bot.loop.create_task(self._gc_loop())

    def cog_unload(self):
        if self._gc_task:
            self._gc_task.cancel()

    async def _gc_loop(self):
        try:
            while True:
                await asyncio.sleep(60)
                now = _now()
                for uid, (_, deadline) in list(ACTIVE_APPEALS.items()):
                    if deadline < now:
                        ACTIVE_APPEALS.pop(uid, None)
        except asyncio.CancelledError:
            pass

    @app_commands.guilds(GUILD_OBJ)
    @app_commands.command(name="ban", description="Bannir un utilisateur avec DM + option de contestation.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user="Utilisateur à bannir",
        reason="Message (UTF-8) envoyé en MP au banni",
        delete_seconds="Supprimer ses messages récents (en secondes, max ~7 jours)",
        notify="Envoyer un MP avant le ban (oui par défaut)",
        allow_appeal="Proposer la contestation (oui par défaut)"
    )
    async def ban(  # <<< ASYNC
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: t.Optional[str] = None,
        delete_seconds: t.Optional[int] = 0,
        notify: bool = True,
        allow_appeal: bool = True,
    ):
        guild = interaction.guild
        assert guild is not None, "À utiliser dans un serveur."
        me = guild.me

        if not me or not me.guild_permissions.ban_members:
            return await interaction.response.send_message(
                "⚠️ Il me manque la permission **Bannir des membres**.", ephemeral=True
            )

        if isinstance(user, discord.Member):
            if user == guild.owner:
                return await interaction.response.send_message("❌ On ne peut pas bannir le propriétaire.", ephemeral=True)
            if user.top_role >= me.top_role and user != me:
                return await interaction.response.send_message("❌ Son rôle est supérieur ou égal au mien.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        dm_failed = False
        token = uuid.uuid4().hex
        if notify:
            try:
                dm = await user.create_dm()
                embed = discord.Embed(
                    title="🚫 Notification de bannissement",
                    description=(
                        f"Tu as été banni(e) de **{guild.name}**.\n\n"
                        + (f"**Message de la modération :**\n{reason}\n\n" if reason else "")
                        + ("Si tu penses qu'il s'agit d'une erreur, tu peux **contester** ci-dessous." if allow_appeal else "")
                    ),
                    color=discord.Color.red(),
                )
                view = AppealView(token=token) if allow_appeal else None
                await dm.send(embed=embed, view=view)
            except Exception:
                dm_failed = True

        delete_days = 0
        if delete_seconds and delete_seconds > 0:
            delete_days = min(7, max(0, delete_seconds // 86400))

        try:
            await guild.ban(user, reason=reason or "Violation des règles", delete_message_days=delete_days)
        except discord.Forbidden:
            return await interaction.followup.send("❌ Permission refusée pour bannir cet utilisateur.", ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"❌ Erreur lors du bannissement : `{e}`", ephemeral=True)

        msg = f"✅ {user.mention} a été banni."
        if notify and dm_failed:
            msg += " (⚠️ MP non remis)"
        await interaction.followup.send(msg, ephemeral=True)

        if allow_appeal and SIGNALEMENT_CHANNEL_ID > 0:
            ch = self.bot.get_channel(SIGNALEMENT_CHANNEL_ID)
            if isinstance(ch, (discord.TextChannel, discord.Thread)):
                embed = discord.Embed(
                    title="🚫 Bannissement exécuté",
                    description=(
                        f"**Utilisateur :** {user} (`{user.id}`)\n"
                        f"**Modérateur :** {interaction.user} (`{interaction.user.id}`)\n"
                        + (f"**Raison :** {reason}\n" if reason else "")
                        + f"**Token de contestation :** `{token}`\n"
                        f"**MP envoyé :** {'oui' if (notify and not dm_failed) else 'non'}\n"
                        f"**Fenêtre :** {APPEAL_WINDOW_SECONDS//60} min"
                    ),
                    color=discord.Color.red(),
                )
                await ch.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def on_message_for_appeal(self, message: discord.Message):  # <<< ASYNC
        if message.guild is not None:
            return
        if message.author.bot:
            return
        if message.author.id not in ACTIVE_APPEALS:
            return

        token, deadline = ACTIVE_APPEALS.get(message.author.id, (None, 0))
        if token is None or _now() > deadline:
            ACTIVE_APPEALS.pop(message.author.id, None)
            try:
                await message.channel.send("⏳ Ta fenêtre de contestation a expiré.")
            except Exception:
                pass
            return

        channel = self.bot.get_channel(SIGNALEMENT_CHANNEL_ID)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            try:
                await message.channel.send("❌ Salon SIGNALEMENT non configuré.")
            except Exception:
                pass
            ACTIVE_APPEALS.pop(message.author.id, None)
            return

        content = message.content.strip() if message.content else "(aucun message texte)"
        embed = discord.Embed(
            title="📨 Contestation de bannissement (DM)",
            description=(
                f"**Utilisateur :** {message.author} (`{message.author.id}`)\n"
                f"**Token :** `{token}`\n\n"
                f"**Message :**\n{content}"
            ),
            color=discord.Color.orange(),
        )

        files: list[discord.File] = []
        for i, att in enumerate(message.attachments[:APPEAL_MAX_ATTACHMENTS], start=1):
            if att.size and att.size > APPEAL_MAX_FORWARD_BYTES:
                embed.add_field(
                    name=f"Fichier {i}",
                    value=f"{att.filename} — trop volumineux ({att.size} octets)",
                    inline=False
                )
                continue
            try:
                f = await att.to_file()
                files.append(f)
            except Exception as e:
                embed.add_field(
                    name=f"Fichier {i}",
                    value=f"{att.filename} — erreur lors du téléchargement : {e}",
                    inline=False
                )

        await channel.send(embed=embed, files=files or None)

        try:
            await message.channel.send("✅ Contestation transmise. Merci.")
        except Exception:
            pass

        ACTIVE_APPEALS.pop(message.author.id, None)

    @ban.error
    async def ban_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):  # <<< ASYNC
        if isinstance(error, app_commands.MissingPermissions):
            return await interaction.response.send_message(
                "❌ Il te manque la permission **Bannir des membres**.", ephemeral=True
            )
        await interaction.response.send_message(f"⚠️ Erreur : {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
