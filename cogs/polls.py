from __future__ import annotations

import contextlib
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

MAX_CHOICES = 10
MAX_QUESTION_LENGTH = 256
MAX_CHOICE_LENGTH = 100
MAX_TIMEOUT_MINUTES = 7 * 24 * 60  # une semaine
CHOICE_EMOJIS = [
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
    "🔟",
]


class Polls(commands.Cog):
    """Gestion des sondages via commandes slash."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sondage", description="Créer un sondage clair avec réactions")
    @app_commands.rename(set_timeout="duree")
    @app_commands.describe(
        question="Intitulé du sondage",
        choix1="Premier choix (obligatoire)",
        choix2="Deuxième choix (obligatoire)",
        choix3="Troisième choix (optionnel)",
        choix4="Quatrième choix (optionnel)",
        choix5="Cinquième choix (optionnel)",
        choix6="Sixième choix (optionnel)",
        choix7="Septième choix (optionnel)",
        choix8="Huitième choix (optionnel)",
        choix9="Neuvième choix (optionnel)",
        choix10="Dixième choix (optionnel)",
        set_timeout="Durée du sondage en minutes (optionnel)",
        salon="Salon où publier le sondage (par défaut : ici)",
    )
    async def sondage(
        self,
        interaction: discord.Interaction,
        question: str,
        choix1: str,
        choix2: str,
        choix3: str | None = None,
        choix4: str | None = None,
        choix5: str | None = None,
        choix6: str | None = None,
        choix7: str | None = None,
        choix8: str | None = None,
        choix9: str | None = None,
        choix10: str | None = None,
        set_timeout: int | None = None,
        salon: discord.TextChannel | None = None,
    ) -> None:
        # validations avant d'accuser réception
        question = question.strip()
        if not question:
            await interaction.response.send_message(
                "⚠️ La question du sondage ne peut pas être vide.", ephemeral=True
            )
            return
        if len(question) > MAX_QUESTION_LENGTH:
            await interaction.response.send_message(
                f"⚠️ La question doit faire moins de {MAX_QUESTION_LENGTH} caractères.",
                ephemeral=True,
            )
            return

        raw_choices = [choix1, choix2, choix3, choix4, choix5, choix6, choix7, choix8, choix9, choix10]
        cleaned_choices: list[str] = []
        seen_casefold: set[str] = set()
        for choice in raw_choices:
            if choice is None:
                continue
            choice_text = choice.strip()
            if not choice_text:
                continue
            if len(choice_text) > MAX_CHOICE_LENGTH:
                await interaction.response.send_message(
                    f"⚠️ Chaque choix doit faire moins de {MAX_CHOICE_LENGTH} caractères.",
                    ephemeral=True,
                )
                return
            key = choice_text.casefold()
            if key in seen_casefold:
                await interaction.response.send_message(
                    "⚠️ Impossible d'ajouter deux fois le même choix.", ephemeral=True
                )
                return
            seen_casefold.add(key)
            cleaned_choices.append(choice_text)

        if len(cleaned_choices) < 2:
            await interaction.response.send_message(
                "⚠️ Merci de proposer au moins deux choix distincts.", ephemeral=True
            )
            return

        if len(cleaned_choices) > MAX_CHOICES:
            await interaction.response.send_message(
                f"⚠️ Impossible de proposer plus de {MAX_CHOICES} choix.",
                ephemeral=True,
            )
            return

        if set_timeout is not None:
            if set_timeout <= 0:
                await interaction.response.send_message(
                    "⚠️ La durée doit être strictement positive.", ephemeral=True
                )
                return
            if set_timeout > MAX_TIMEOUT_MINUTES:
                await interaction.response.send_message(
                    "⚠️ La durée maximale d'un sondage est de 7 jours (10080 minutes).",
                    ephemeral=True,
                )
                return

        target_channel: discord.abc.MessageableChannel | None
        if salon is not None:
            if interaction.guild is None:
                await interaction.response.send_message(
                    "⚠️ Impossible de cibler un salon depuis un message privé.",
                    ephemeral=True,
                )
                return
            if salon.guild != interaction.guild:
                await interaction.response.send_message(
                    "⚠️ Le salon doit appartenir au même serveur que la commande.",
                    ephemeral=True,
                )
                return
            target_channel = salon
        else:
            target_channel = interaction.channel

        if target_channel is None:
            await interaction.response.send_message(
                "⚠️ Impossible de déterminer le salon de publication.", ephemeral=True
            )
            return

        # Vérification des permissions du bot dans le salon cible
        if isinstance(target_channel, discord.abc.GuildChannel):
            me = target_channel.guild.me
            if me is not None:
                permissions = target_channel.permissions_for(me)
                if not permissions.view_channel:
                    await interaction.response.send_message(
                        "⚠️ Je n'ai pas accès au salon ciblé.", ephemeral=True
                    )
                    return
                if not permissions.send_messages:
                    await interaction.response.send_message(
                        "⚠️ Je n'ai pas la permission d'envoyer un message dans ce salon.",
                        ephemeral=True,
                    )
                    return
                if isinstance(target_channel, discord.Thread) and not permissions.send_messages_in_threads:
                    await interaction.response.send_message(
                        "⚠️ Je ne peux pas écrire dans ce fil de discussion.",
                        ephemeral=True,
                    )
                    return
                if not permissions.add_reactions:
                    await interaction.response.send_message(
                        "⚠️ Je ne peux pas ajouter de réactions dans ce salon.",
                        ephemeral=True,
                    )
                    return
                if not permissions.embed_links:
                    await interaction.response.send_message(
                        "⚠️ J'ai besoin de la permission d'intégrer des liens pour afficher le sondage.",
                        ephemeral=True,
                    )
                    return

        end_time = None
        if set_timeout is not None:
            end_time = discord.utils.utcnow() + timedelta(minutes=set_timeout)

        embed = discord.Embed(
            title="📊 Nouveau sondage",
            description=f"{question}\n\nRéagissez avec l'emoji correspondant pour voter.",
            color=discord.Color.blurple(),
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )

        for index, choice_text in enumerate(cleaned_choices, start=1):
            emoji = CHOICE_EMOJIS[index - 1]
            embed.add_field(
                name=f"{emoji} Choix {index}",
                value=choice_text,
                inline=False,
            )

        if end_time is not None:
            absolute_end = discord.utils.format_dt(end_time, style="f")
            relative_end = discord.utils.format_dt(end_time, style="R")
            embed.set_footer(text=f"Se termine {absolute_end} ({relative_end})")
            embed.timestamp = end_time
        else:
            embed.set_footer(text="Aucune durée définie")

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            poll_message = await target_channel.send(
                content=f"Sondage proposé par {interaction.user.mention}",
                embed=embed,
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                f"⚠️ Impossible de publier le sondage : {exc}", ephemeral=True
            )
            return

        try:
            for emoji in CHOICE_EMOJIS[: len(cleaned_choices)]:
                await poll_message.add_reaction(emoji)
        except discord.HTTPException as exc:
            with contextlib.suppress(discord.HTTPException):
                await poll_message.delete()
            await interaction.followup.send(
                "⚠️ Le sondage a été créé mais impossible d'ajouter les réactions "
                f"({exc}). Merci de vérifier mes permissions.",
                ephemeral=True,
            )
            return

        location: str
        if isinstance(target_channel, discord.abc.GuildChannel):
            location = target_channel.mention
        else:
            location = "cette conversation"

        summary_parts = [f"✅ Sondage publié dans {location}"]
        if end_time is not None:
            formatted_end = discord.utils.format_dt(end_time, style="f")
            relative_end = discord.utils.format_dt(end_time, style="R")
            summary_parts.append(f"Fin {formatted_end} ({relative_end})")
        else:
            summary_parts.append("Durée indéterminée")

        if set_timeout is not None:
            summary_parts.append(f"setTimeOut : {set_timeout} minute(s)")

        await interaction.followup.send(
            " • ".join(summary_parts) + f"\n{poll_message.jump_url}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
