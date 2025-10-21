from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import discord
from discord import app_commands
from discord.ext import commands

MAX_CHOICES = 10
MAX_QUESTION_LENGTH = 256
MAX_CHOICE_LENGTH = 100
MAX_TIMEOUT_MINUTES = 7 * 24 * 60  # une semaine
BAR_SIZE = 20  # largeur des barres de progression

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


def make_bar(pct: float, size: int = BAR_SIZE) -> str:
    """Barre de progression textuelle."""
    pct = max(0.0, min(1.0, pct))
    filled = int(round(pct * size))
    return "█" * filled + "░" * (size - filled)


def parse_choice_line(line: str) -> Tuple[Optional[Union[str, discord.PartialEmoji]], str]:
    """
    Parse une ligne 'emoji optionnel + espace + libellé'.
    - Supporte les émojis Unicode (🥐) et custom (<:name:id>).
    - Retourne (emoji|None, label).
    """
    s = line.strip()
    if not s:
        return None, ""
    # émoji custom ?
    if s.startswith("<") and ">" in s:
        maybe = s.split(">", 1)[0] + ">"
        try:
            pe = discord.PartialEmoji.from_str(maybe)
            label = s[len(maybe):].strip()
            return pe, label
        except Exception:
            pass
    # Unicode au début (très permissif : on prend le premier grapheme avant espace)
    parts = s.split(" ", 1)
    if len(parts) == 2 and parts[0]:
        first, rest = parts
        # heuristique : si rest non vide et first contient un codepoint non alphanum, on le traite comme emoji
        if not first.isalnum():
            return first, rest.strip()
    # pas d’emoji détecté
    return None, s

# --------------------------------------------------------------------------- #
# Modèle
# --------------------------------------------------------------------------- #


@dataclass
class Choice:
    label: str
    emoji: Optional[Union[str, discord.PartialEmoji]] = None


@dataclass
class PollState:
    question: str
    choices: List[Choice]
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
# Views
# --------------------------------------------------------------------------- #


class PollButton(discord.ui.Button):
    def __init__(self, index: int, choice: Choice):
        # On n’affiche PAS de label, seulement l’emoji si fourni
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=None,
            emoji=choice.emoji,
            row=min(index // 5, 4),  # 5 boutons par ligne max
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        cog: Polls = self.view.cog  # type: ignore
        state: PollState = self.view.state  # type: ignore

        if state.end_time and discord.utils.utcnow() >= state.end_time:
            return await interaction.response.send_message(
                "⏰ Le sondage est déjà terminé.", ephemeral=True
            )

        user_id = interaction.user.id
        previous = state.votes.get(user_id)
        state.votes[user_id] = self.index
        changed = (previous != self.index)

        # MAJ embed
        if state.channel_id and state.message_id:
            channel = cog.bot.get_channel(state.channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                try:
                    msg = await channel.fetch_message(state.message_id)
                except discord.HTTPException:
                    return
                embed = cog.build_running_embed(state, interaction.user)
                with contextlib.suppress(discord.HTTPException):
                    await msg.edit(embed=embed)

        # Feedback
        choice = state.choices[self.index]
        if changed:
            await interaction.response.send_message(
                f"✅ Vote enregistré pour **{choice.label}**.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "ℹ️ Tu avais déjà sélectionné ce choix.", ephemeral=True
            )


class PollView(discord.ui.View):
    def __init__(self, cog: "Polls", state: PollState, *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.state = state
        for i, choice in enumerate(state.choices):
            self.add_item(PollButton(index=i, choice=choice))

    async def on_timeout(self) -> None:
        # Sécurité si jamais la View time-out : on clôture proprement
        if self.state.message_id and self.state.channel_id:
            channel = self.cog.bot.get_channel(self.state.channel_id)
            if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
                with contextlib.suppress(Exception):
                    msg = await channel.fetch_message(self.state.message_id)
                    await self.cog.finalize_poll(msg, self.state)

# --------------------------------------------------------------------------- #
# Modal + starter
# --------------------------------------------------------------------------- #


class PollModal(discord.ui.Modal, title="Créer un sondage"):
    question = discord.ui.TextInput(
        label="Question du sondage",
        placeholder="Ex : Quelle viennoiserie préférez-vous ?",
        max_length=MAX_QUESTION_LENGTH,
    )
    options = discord.ui.TextInput(
        label="Choix (1 par ligne, émoji optionnel au début)",
        style=discord.TextStyle.paragraph,
        placeholder="Ex :\n🥐 Croissant\n🍫 Pain au chocolat\n<:baguette:112233445566778899> Baguette",
    )
    duree = discord.ui.TextInput(
        label="Durée en minutes (optionnel)",
        required=False,
        placeholder="Ex : 60",
    )

    def __init__(self, cog: "Polls"):
        super().__init__(timeout=None)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        q = self.question.value.strip()
        if not q:
            return await interaction.response.send_message("⚠️ La question ne peut pas être vide.", ephemeral=True)

        lines = [l.strip()
                 for l in str(self.options.value).splitlines() if l.strip()]
        if len(lines) < 2:
            return await interaction.response.send_message("⚠️ Mets au moins deux choix.", ephemeral=True)
        if len(lines) > MAX_CHOICES:
            return await interaction.response.send_message(f"⚠️ Maximum {MAX_CHOICES} choix.", ephemeral=True)

        choices: List[Choice] = []
        seen = set()
        for line in lines:
            emoji, label = parse_choice_line(line)
            if not label:
                return await interaction.response.send_message("⚠️ Un des choix est vide.", ephemeral=True)
            if len(label) > MAX_CHOICE_LENGTH:
                return await interaction.response.send_message(
                    f"⚠️ Chaque choix doit faire moins de {MAX_CHOICE_LENGTH} caractères.",
                    ephemeral=True,
                )
            key = label.casefold()
            if key in seen:
                return await interaction.response.send_message("⚠️ Choix en double détecté.", ephemeral=True)
            seen.add(key)
            choices.append(Choice(label=label, emoji=emoji))

        d_minutes: Optional[int] = None
        if self.duree.value.strip():
            if not self.duree.value.strip().isdigit():
                return await interaction.response.send_message("⚠️ La durée doit être un nombre en minutes.", ephemeral=True)
            d_minutes = int(self.duree.value.strip())
            if d_minutes <= 0:
                return await interaction.response.send_message("⚠️ La durée doit être positive.", ephemeral=True)
            if d_minutes > MAX_TIMEOUT_MINUTES:
                return await interaction.response.send_message("⚠️ Durée max : 7 jours (10080 minutes).", ephemeral=True)

        await self.cog.create_poll(interaction, q, choices, d_minutes)


class PollStarter(discord.ui.View):
    def __init__(self, cog: "Polls"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Créer un sondage 🗳️", style=discord.ButtonStyle.success)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PollModal(self.cog))

# --------------------------------------------------------------------------- #
# Cog
# --------------------------------------------------------------------------- #


class Polls(commands.Cog):
    """Sondages avec Modal + boutons émojis + barres de progression et timer."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
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

        for ch, c in zip(state.choices, counts):
            pct = (c / total) if total > 0 else 0.0
            bar = make_bar(pct)
            pct_txt = f"{int(round(pct * 100))}%"
            prefix = f"{ch.emoji} " if ch.emoji else ""
            emb.add_field(name=f"{prefix}{ch.label}",
                          value=f"{bar}  **{c}** vote(s) • {pct_txt}", inline=False)

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

        for ch, c in zip(state.choices, counts):
            pct = (c / total) if total > 0 else 0.0
            bar = make_bar(pct)
            pct_txt = f"{int(round(pct * 100))}%"
            prefix = f"{ch.emoji} " if ch.emoji else ""
            emb.add_field(name=f"{prefix}{ch.label}",
                          value=f"{bar}  **{c}** vote(s) • {pct_txt}", inline=False)

        emb.set_footer(text=f"{total} vote(s) • Sondage terminé")
        return emb

    # ------------------------------ Core ---------------------------------- #

    async def run_countdown_and_close(self, message: discord.Message, state: PollState):
        """MAJ du footer chaque seconde puis clôture et verrouillage des boutons."""
        if not state.end_time:
            return

        while True:
            now = discord.utils.utcnow()
            remaining = int((state.end_time - now).total_seconds())
            if remaining <= 0:
                break
            embed = self.build_running_embed(state, message.author)
            with contextlib.suppress(discord.HTTPException):
                await message.edit(embed=embed)
            await asyncio.sleep(1)

        await self.finalize_poll(message, state)

    async def finalize_poll(self, message: discord.Message, state: PollState):
        """Remplace l’embed par les résultats et désactive tous les boutons."""
        # Re-crée une view identique mais disabled
        try:
            view = PollView(self, state)
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
        except Exception:
            view = None

        closed = self.build_closed_embed(state, message.author)
        with contextlib.suppress(discord.HTTPException):
            await message.edit(content="**Sondage terminé** ⏰", embed=closed, view=view)

    async def create_poll(
        self,
        interaction: discord.Interaction,
        question: str,
        choices: List[Choice],
        duree_minutes: Optional[int],
    ):
        # Salon cible
        target = interaction.channel
        if target is None:
            return await interaction.response.send_message(
                "⚠️ Impossible de déterminer le salon de publication.", ephemeral=True
            )

        # Permissions minimales
        if isinstance(target, discord.abc.GuildChannel):
            me = target.guild.me
            if me is not None:
                perms = target.permissions_for(me)
                if not perms.view_channel or not perms.send_messages or not perms.embed_links:
                    return await interaction.response.send_message(
                        "⚠️ Il me manque des permissions (voir/envoyer/intégrer).",
                        ephemeral=True,
                    )

        end_time = discord.utils.utcnow(
        ) + timedelta(minutes=duree_minutes) if duree_minutes else None
        state = PollState(
            question=question,
            choices=choices,
            author_id=interaction.user.id,
            end_time=end_time,
        )
        embed = self.build_running_embed(state, interaction.user)
        view = PollView(self, state, timeout=None)

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            msg = await target.send(
                content=f"Sondage proposé par {interaction.user.mention}",
                embed=embed,
                view=view,
            )
        except discord.HTTPException as exc:
            return await interaction.followup.send(
                f"⚠️ Impossible de publier le sondage : {exc}", ephemeral=True
            )

        state.message_id = msg.id
        state.channel_id = msg.channel.id
        self._sessions[msg.id] = state

        loc = target.mention if isinstance(
            target, discord.abc.GuildChannel) else "cette conversation"
        parts = [f"✅ Sondage publié dans {loc}"]
        if end_time:
            parts.append(
                f"Fin dans {fmt_remaining(int((end_time - discord.utils.utcnow()).total_seconds()))}")
        else:
            parts.append("Durée indéterminée")

        await interaction.followup.send(" • ".join(parts) + f"\n{msg.jump_url}", ephemeral=True)

        if end_time:
            asyncio.create_task(self.run_countdown_and_close(msg, state))

    # ------------------------------ Slash cmd ----------------------------- #

    @app_commands.command(name="sondage", description="Ouvrir le formulaire de création de sondage (avec émojis)")
    async def sondage(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Clique sur le bouton ci-dessous pour créer ton sondage 👇",
            view=PollStarter(self),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
