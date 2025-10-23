# cogs/moderation.py
# -*- coding: utf-8 -*-
import os
import time
import uuid
import typing as t
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from config import GUILD_ID

# ---------- CONFIG ----------
# Mets l'ID du salon où recevoir les contestations (ou via .env)
SIGNALEMENT_CHANNEL_ID = int(os.getenv("SIGNALEMENT_CHANNEL_ID", "0"))

# Limites anti-abus pour la contestation
# 10 minutes pour répondre après avoir cliqué le bouton
APPEAL_WINDOW_SECONDS = 10 * 60
APPEAL_MAX_ATTACHMENTS = 5               # max 5 fichiers
# 25 Mo par fichier (dépend de la limite de ton serveur)
APPEAL_MAX_FORWARD_BYTES = 25 * 1024**2
# ----------------------------

# Mémoire simple en RAM : user_id -> (token, deadline_ts)
# Quand l’utilisateur clique sur "Contester", on l’ajoute ici. Le prochain MP qu’il envoie sera routé au salon.
ACTIVE_APPEALS: dict[int, tuple[str, float]] = {}


def _now() -> float:
    return time.time()


class AppealView(discord.ui.View):
    """Bouton en DM pour ouvrir une fenêtre de contestation (texte + pièces jointes en MP)."""

    def __init__(self, token: str):
        super().__init__(timeout=None)
        self.token = token

    @discord.ui.button(label="Contester mon bannissement", style=discord.ButtonStyle.primary, custom_id="appeal_open")
    async def appeal_open(self, interaction: discord.Interaction, _: discord.ui.Button):
        # On arme la fenêtre de contestation : l’utilisateur doit envoyer son message + fichiers en MP
        ACTIVE_APPEALS[interaction.user.id] = (
            self.token, _now() + APPEAL_WINDOW_SECONDS)
        await interaction.response.send_message(
            (
                "📝 Merci d’écrire **ta contestation** dans ce MP (tu peux joindre "
                "des **fichiers audio/vidéo/images**). "
                f"Tu as **{APPEAL_WINDOW_SECONDS//60} minutes**.\n\n"
                "→ Envoie un **seul message** avec tout ce que tu veux transmettre."
            ),
            ephemeral=True
        )


class Moderation(commands.Cog):
    """Commandes de modération : /ban avec DM + contestation (texte + fichiers)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Démarre une tâche de nettoyage périodique (expire les fenêtres d'appel)
        self._gc_task = bot.loop.create_task(self._gc_loop())

    def cog_unload(self):
        if self._gc_task:
            self._gc_task.cancel()

    async def _gc_loop(self):
        try:
            while True:
                await asyncio.sleep(60)
                now = _now()
                to_del = [
                    uid for uid, (_, deadline) in ACTIVE_APPEALS.items() if deadline < now]
                for uid in to_del:
                    ACTIVE_APPEALS.pop(uid, None)
        except asyncio.CancelledError:
            pass

    # ============ SLASH: /ban ============
    @app_commands.command(name="ban", description="Bannir un utilisateur avec DM et option de contestation.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user="Utilisateur à bannir",
        reason="Message (UTF-8) envoyé en MP au banni (facultatif).",
        delete_seconds="Supprimer ses messages récents (en secondes, défaut 0, max ~7 jours).",
        notify="Tenter d'envoyer un MP avant le ban (oui par défaut).",
        allow_appeal="Proposer la contestation par MP (oui par défaut)."
    )
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.command(name="ban")
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        reason: t.Optional[str] = None,
        delete_seconds: t.Optional[int] = 0,
        notify: bool = True,
        allow_appeal: bool = True,
    ):
        guild = interaction.guild
        assert guild is not None, "Cette commande s'utilise dans un serveur."
        me = guild.me

        if not me or not me.guild_permissions.ban_members:
            return await interaction.response.send_message("⚠️ Il me manque la permission **Bannir des membres**.", ephemeral=True)

        # Empêcher des cas classiques
        if isinstance(user, discord.Member):
            if user == guild.owner:
                return await interaction.response.send_message("❌ Impossible de bannir le propriétaire.", ephemeral=True)
            if user.top_role >= me.top_role and user != me:
                return await interaction.response.send_message("❌ Son rôle est supérieur ou égal au mien.", ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        # Préparer le DM
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
            except discord.Forbidden:
                dm_failed = True
            except Exception:
                dm_failed = True

        # Exécuter le ban (on convertit secondes -> jours pour compat rétro)
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

        # Journal côté modération (création fenêtre d’appel)
        if allow_appeal and SIGNALEMENT_CHANNEL_ID > 0:
            ch = self.bot.get_channel(SIGNALEMENT_CHANNEL_ID)
            if isinstance(ch, (discord.TextChannel, discord.Thread)):
                embed = discord.Embed(
                    title="🚫 Bannissement exécuté",
                    description=(
                        f"**Utilisateur :** {user} (`{user.id}`)\n"
                        f"**Modérateur :** {interaction.user} (`{interaction.user.id}`)\n"
                        + (f"**Raison :** {reason}\n" if reason else "")
                        + f"**Token pour contestation :** `{token}`\n"
                        f"**MP envoyé :** {'oui' if (notify and not dm_failed) else 'non'}\n"
                        f"**Fenêtre de contestation :** {APPEAL_WINDOW_SECONDS//60} min"
                    ),
                    color=discord.Color.red(),
                )
                await ch.send(embed=embed)

    # ============ ROUTAGE DES MESSAGES DM POUR CONTESTATION ============
    @commands.Cog.listener("on_message")
    async def on_message_for_appeal(self, message: discord.Message):
        # On ne traite que les MP, non-bot, et seulement si l'utilisateur a une fenêtre active
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
                await message.channel.send("⏳ Ta fenêtre de contestation a expiré. Demande à un modo de te rouvrir l’accès.")
            except Exception:
                pass
            return

        # Récupérer le salon cible
        channel = self.bot.get_channel(SIGNALEMENT_CHANNEL_ID)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            try:
                await message.channel.send("❌ Le serveur n’a pas encore configuré le salon de signalement.")
            except Exception:
                pass
            ACTIVE_APPEALS.pop(message.author.id, None)
            return

        # Construire l’embed (texte UTF-8 natif en Python)
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
        # Joindre jusqu’à APPEAL_MAX_ATTACHMENTS pièces jointes (audio/vidéo/images)
        for i, att in enumerate(message.attachments[:APPEAL_MAX_ATTACHMENTS], start=1):
            if att.size and att.size > APPEAL_MAX_FORWARD_BYTES:
                # On indique qu’un fichier dépasse la taille autorisée
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

        # Poster au salon de signalement
        await channel.send(embed=embed, files=files if files else None)

        # Accuser réception au banni
        try:
            await message.channel.send("✅ Ta contestation a bien été transmise à l’équipe de modération. Merci.")
        except Exception:
            pass

        # Fermer la fenêtre (un seul message traité)
        ACTIVE_APPEALS.pop(message.author.id, None)

    # Gestion erreurs slash
    @ban.error
    async def ban_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            return await interaction.response.send_message(
                "❌ Il te manque la permission **Bannir des membres**.", ephemeral=True
            )
        await interaction.response.send_message(f"⚠️ Erreur : {error}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
