from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

MAX_CHOICES = 10
MAX_QUESTION_LENGTH = 256
MAX_CHOICE_LENGTH = 100
MAX_TIMEOUT_MINUTES = 7 * 24 * 60  # une semaine

# --------------------------------------------------------------------------- #
# Helpers d'affichage
# --------------------------------------------------------------------------- #


def fmt_remaining(seconds: int) -> str:
    """HH:MM:SS (ou MM:SS si < 1h)."""
    if seconds < 0:
        seconds = 0
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def make_bar(pct: float, size: int = 20) -> str:
    """Barre de progression textuelle."""
    pct = max(0.0, min(1.0, pct))
    filled = int(round(pct * size))
    return "█" * filled + "░" * (size - filled)

# --------------------------------------------------------------------------- #
# Modèle de session de sondage (en mémoire)
# --------------------------------------------------------------------------- #


@dataclass
class PollState:
    question: str
    choices: List[str]
    author_id: int
    end_time: Optional[datetime] = None
    message_id: Optional[int] = None
    channel_id: Optional[int] = None
    # votes[user_id] = index du choix
    votes: Dict[int, int] = field(default_factory=dict)

    @property
    def counts(self) -> List[int]:
        c = [0] * len(self.choices)
        for idx in self.votes.values():
            if 0 <= idx < len(c):
                c[idx] += 1
        return c

    @property
    def total(self) -> int:
        return sum(self.counts)

# --------------------------------------------------------------------------- #
# Vue (boutons) pour le sondage
# --------------------------------------------------------------------------- #


class PollView(discord.ui.View):
    def __init__(self, cog: "Polls", state: PollState, *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.state = state
        # Crée un bouton par choix
        for i, label in enumerate(state.choices, start=1):
            self.add_item(PollButton(index=i-1, label_text=label))

    async def on_timeout(self) -> None:
        # Si la vue time-out (peu probable car on pilote via end_time),
        # on clôture côté cog pour figer l’UI.
        if self.state.message_id and self.state.channel_id:
            channel = self.cog.bot.get_channel(self.state.channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                with contextlib.suppress(Exception):
                    msg = await channel.fetch_message(self.state.message_id)
                    await self.cog.finalize_poll(msg, self.state)


class PollButton(discord.ui.Button):
    def __init__(self, index: int, label_text: str):
        # style par défaut ; on n’affiche pas les votes ici (ils sont dans l’embed)
        super().__init__(style=discord.ButtonStyle.primary,
                         label=label_text, row=min(index // 3, 4))
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        cog: Polls = self.view.cog  # type: ignore
        state: PollState = self.view.state  # type: ignore

        # Empêcher les votes si terminé
        if state.end_time and discord.utils.utcnow() >= state.end_time:
            return await interaction.response.send_message(
                "⏰ Le sondage est déjà terminé.", ephemeral=True
            )

        user_id = interaction.user.id
        # Enregistrer/mettre à jour le vote
        previous = state.votes.get(user_id)
        state.votes[user_id] = self.index
        changed = (previous != self.index)

        # MAJ embed + contenu
        if state.channel_id and state.message_id:
            channel = cog.bot.get_channel(state.channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                try:
                    msg = await channel.fetch_message(state.message_id)
                except discord.HTTPException:
                    return
                embed = cog.build_running_embed(
                    state, msg.author if hasattr(msg, "author") else interaction.user)
                with contextlib.suppress(discord.HTTPException):
                    await msg.edit(embed=embed)

        # Confirme au votant (éphémère)
        if changed:
            await interaction.response.send_message(
                f"✅ Vote enregistré pour **{state.choices[self.index]}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "ℹ️ Tu avais déjà sélectionné ce choix.", ephemeral=True
            )

# --------------------------------------------------------------------------- #
# Le Cog principal
# --------------------------------------------------------------------------- #


class Polls(commands.Cog):
    """Gestion des sondages via commandes slash (UI boutons + barres)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # message_id -> PollState
        self._sessions: Dict[int, PollState] = {}

    # ------------------------------ Embeds -------------------------------- #

    def build_running_embed(self, state: PollState, author: discord.abc.User) -> discord.Embed:
        counts = state.counts
        total = sum(counts)
        emb = discord.Embed(
            title="📊 Nouveau sondage",
            description=f"{state.question}\n\nCliquez sur un bouton pour voter.",
            color=discord.Color.blurple(),
        )
        emb.set_author(
            name=getattr(author, "display_name", "Auteur"),
            icon_url=getattr(
                getattr(author, "display_avatar", None), "url", None),
        )

        for label, c in zip(state.choices, counts):
            pct = (c / total) if total > 0 else 0.0
            bar = make_bar(pct)
            pct_txt = f"{int(round(pct * 100))}%"
            emb.add_field(
                name=label, value=f"{bar}  **{c}** vote(s) • {pct_txt}", inline=False)

        # Footer (compte à rebours si end_time)
        if state.end_time:
            remaining = int(
                (state.end_time - discord.utils.utcnow()).total_seconds())
            emb.set_footer(text=f"Se termine dans {fmt_remaining(remaining)}")
        else:
            emb.set_footer(text="Aucune durée définie")
        return emb

    def build_closed_embed(self, state: PollState, author: discord.abc.User) -> discord.Embed:
        counts = state.counts
        total = sum(counts)
        emb = discord.Embed(
            title="📊 Sondage terminé",
            description="Voici les résultats :",
            color=discord.Color.dark_gray(),
        )
        emb.set_author(
            name=getattr(author, "display_name", "Auteur"),
            icon_url=getattr(
                getattr(author, "display_avatar", None), "url", None),
        )

        for label, c in zip(state.choices, counts):
            pct = (c / total) if total > 0 else 0.0
            bar = make_bar(pct)
            pct_txt = f"{int(round(pct * 100))}%"
            emb.add_field(
                name=label, value=f"{bar}  **{c}** vote(s) • {pct_txt}", inline=False)

        emb.set_footer(text=f"{total} vote(s) • Sondage terminé")
        return emb

    # ------------------------------ Countdown ----------------------------- #

    async def run_countdown_and_close(self, message: discord.Message, state: PollState):
        """MAJ du footer chaque seconde puis clôture et verrouillage des boutons."""
        if not state.end_time:
            return

        while True:
            now = discord.utils.utcnow()
            remaining = int((state.end_time - now).total_seconds())
            if remaining <= 0:
                break

            # MAJ embed
            embed = self.build_running_embed(state, message.author)
            with contextlib.suppress(discord.HTTPException):
                await message.edit(embed=embed)

            await asyncio.sleep(1)

        # Clôture
        await self.finalize_poll(message, state)

    async def finalize_poll(self, message: discord.Message, state: PollState):
        """Remplace l’embed par les résultats et désactive tous les boutons."""
        # Récupérer la view et la désactiver
        try:
            # On re-bâtit une view identique mais disabled
            view = PollView(self, state)
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
        except Exception:
            view = None

        # Éditer le message
        closed = self.build_closed_embed(state, message.author)
        with contextlib.suppress(discord.HTTPException):
            await message.edit(content="**Sondage terminé** ⏰", embed=closed, view=view)

    # ------------------------------ Slash cmd ----------------------------- #

    @app_commands.command(name="sondage", description="Créer un sondage avec boutons et barres de progression")
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
        # --- validations basiques ---
        question = question.strip()
        if not question:
            return await interaction.response.send_message(
                "⚠️ La question du sondage ne peut pas être vide.", ephemeral=True
            )
        if len(question) > MAX_QUESTION_LENGTH:
            return await interaction.response.send_message(
                f"⚠️ La question doit faire moins de {MAX_QUESTION_LENGTH} caractères.", ephemeral=True
            )

        raw = [choix1, choix2, choix3, choix4, choix5,
               choix6, choix7, choix8, choix9, choix10]
        cleaned: List[str] = []
        seen = set()
        for ch in raw:
            if not ch:
                continue
            t = ch.strip()
            if not t:
                continue
            if len(t) > MAX_CHOICE_LENGTH:
                return await interaction.response.send_message(
                    f"⚠️ Chaque choix doit faire moins de {MAX_CHOICE_LENGTH} caractères.", ephemeral=True
                )
            k = t.casefold()
            if k in seen:
                return await interaction.response.send_message(
                    "⚠️ Impossible d'ajouter deux fois le même choix.", ephemeral=True
                )
            seen.add(k)
            cleaned.append(t)

        if len(cleaned) < 2:
            return await interaction.response.send_message(
                "⚠️ Merci de proposer au moins deux choix distincts.", ephemeral=True
            )
        if len(cleaned) > MAX_CHOICES:
            return await interaction.response.send_message(
                f"⚠️ Impossible de proposer plus de {MAX_CHOICES} choix.", ephemeral=True
            )

        if set_timeout is not None:
            if set_timeout <= 0:
                return await interaction.response.send_message(
                    "⚠️ La durée doit être strictement positive.", ephemeral=True
                )
            if set_timeout > MAX_TIMEOUT_MINUTES:
                return await interaction.response.send_message(
                    "⚠️ La durée maximale d'un sondage est de 7 jours (10080 minutes).", ephemeral=True
                )

        # --- salon cible ---
        if salon is not None:
            if interaction.guild is None or salon.guild != interaction.guild:
                return await interaction.response.send_message(
                    "⚠️ Le salon doit appartenir au même serveur que la commande.", ephemeral=True
                )
            target = salon
        else:
            target = interaction.channel

        if target is None:
            return await interaction.response.send_message(
                "⚠️ Impossible de déterminer le salon de publication.", ephemeral=True
            )

        # --- permissions minimales (plus besoin d'add_reactions) ---
        if isinstance(target, discord.abc.GuildChannel):
            me = target.guild.me
            if me is not None:
                perms = target.permissions_for(me)
                if not perms.view_channel or not perms.send_messages or not perms.embed_links:
                    return await interaction.response.send_message(
                        "⚠️ Il me manque des permissions (voir/envoyer/intégrer).", ephemeral=True
                    )

        # --- préparation état & embed ---
        end_time = discord.utils.utcnow(
        ) + timedelta(minutes=set_timeout) if set_timeout else None
        state = PollState(
            question=question,
            choices=cleaned,
            author_id=interaction.user.id,
            end_time=end_time,
        )
        embed = self.build_running_embed(state, interaction.user)

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        # --- envoi + vue (boutons) ---
        view = PollView(self, state, timeout=None)
        try:
            msg = await target.send(content=f"Sondage proposé par {interaction.user.mention}", embed=embed, view=view)
        except discord.HTTPException as exc:
            return await interaction.followup.send(
                f"⚠️ Impossible de publier le sondage : {exc}", ephemeral=True
            )

        state.message_id = msg.id
        state.channel_id = msg.channel.id
        self._sessions[msg.id] = state

        # résumé éphémère
        loc = target.mention if isinstance(
            target, discord.abc.GuildChannel) else "cette conversation"
        parts = [f"✅ Sondage publié dans {loc}"]
        if end_time:
            parts.append(
                f"Fin dans {fmt_remaining(int((end_time - discord.utils.utcnow()).total_seconds()))}")
        else:
            parts.append("Durée indéterminée")

        await interaction.followup.send(" • ".join(parts) + f"\n{msg.jump_url}", ephemeral=True)

        # --- compte à rebours + clôture ---
        if end_time:
            asyncio.create_task(self.run_countdown_and_close(msg, state))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
