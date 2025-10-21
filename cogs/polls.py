from __future__ import annotations

from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

MAX_CHOICES = 10
MAX_QUESTION_LENGTH = 256
MAX_CHOICE_LENGTH = 100
MAX_TIMEOUT_MINUTES = 7 * 24 * 60  # une semaine


class Polls(commands.Cog):
    """Gestion des sondages via commandes slash."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sondage", description="Créer un sondage natif Discord")
    @app_commands.rename(set_timeout="setTimeOut")
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

        if not all(
            hasattr(discord, attr)
            for attr in ("Poll", "PollAnswer", "PollMedia", "PollDuration")
        ):
            await interaction.response.send_message(
                "⚠️ Cette version du bot ne supporte pas les sondages natifs Discord.",
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

        end_time = None
        if set_timeout is not None:
            end_time = discord.utils.utcnow() + timedelta(minutes=set_timeout)

        poll_answers: list[discord.PollAnswer] = [
            discord.PollAnswer(text=discord.PollMedia(text=choice_text))
            for choice_text in cleaned_choices
        ]

        poll_duration: discord.PollDuration | None = None
        if set_timeout is not None:
            poll_duration = discord.PollDuration(minutes=set_timeout)

        poll = discord.Poll(
            question=discord.PollMedia(text=question),
            answers=poll_answers,
            allow_multiselect=False,
            duration=poll_duration,
        )

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            poll_message = await target_channel.send(
                content=f"Sondage proposé par **{interaction.user.display_name}**",
                poll=poll,
            )
        except Exception as exc:  # pragma: no cover - dépend de l'API Discord
            await interaction.followup.send(
                f"⚠️ Impossible de publier le sondage : {exc}", ephemeral=True
            )
            return

        summary_parts = [f"✅ Sondage publié dans {target_channel.mention}"]
        if end_time is not None:
            formatted_end = discord.utils.format_dt(end_time, style="f")
            relative_end = discord.utils.format_dt(end_time, style="R")
            summary_parts.append(f"Fin {formatted_end} ({relative_end})")
        else:
            summary_parts.append("Durée indéterminée")

        if set_timeout is not None:
            summary_parts.append(f"setTimeOut : {set_timeout} minute(s)")

        await interaction.followup.send(
            " • ".join(summary_parts) + f"\n{poll_message.jump_url}",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
