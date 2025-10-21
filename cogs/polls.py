from __future__ import annotations

import asyncio
import contextlib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

import discord
from discord import app_commands
from discord.ext import commands

# =========================
#           CONFIG
# =========================

MAX_CHOICES = 10
MAX_QUESTION_LENGTH = 256
MAX_CHOICE_LENGTH = 100
MAX_TIMEOUT_MINUTES = 7 * 24 * 60  # 1 semaine

# ====== THEME / STYLE ======
THEMES = {
    "gamer": {
        "color_running": discord.Color.from_rgb(88, 101, 242),   # blurple
        "color_closed": discord.Color.from_rgb(32, 34, 37),      # dark gray
        "title_running": "📊 Nouveau sondage",
        "title_closed":  "🏁 Sondage terminé",
        "banner_url": None,  # mets ici une URL d'image si tu veux une bannière
    },
    "pastel": {
        "color_running": discord.Color.from_rgb(255, 179, 186),
        "color_closed": discord.Color.from_rgb(255, 223, 186),
        "title_running": "🧁 Nouveau sondage",
        "title_closed":  "🎀 Sondage terminé",
        "banner_url": None,
    },
    "minimal": {
        "color_running": discord.Color.light_grey(),
        "color_closed": discord.Color.dark_grey(),
        "title_running": "Sondage",
        "title_closed":  "Sondage terminé",
        "banner_url": None,
    },
}
ACTIVE_THEME = "gamer"

# Barres de progression
BAR_SIZE = 14
BAR_FULL = "▰"
BAR_EMPTY = "▱"

# =========================
#         HELPERS
# =========================


def fmt_remaining(seconds: int) -> str:
    """HH:MM:SS (ou MM:SS si <1h)."""
    if seconds < 0:
        seconds = 0
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def make_bar(pct: float, size: int = BAR_SIZE) -> str:
    """Barre ▰▱ alignée."""
    pct = max(0.0, min(1.0, pct))
    filled = int(round(pct * size))
    return BAR_FULL * filled + BAR_EMPTY * (size - filled)


def medal_for(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "•")


def looks_like_unicode_emoji(token: str) -> bool:
    """Heuristique simple pour différencier un vrai emoji d’un texte."""
    if not token or token.isalnum():
        return False
    return any(unicodedata.category(ch) in ("So", "Sk") for ch in token)


def coerce_emoji(val: Union[str, discord.PartialEmoji, None]) -> Optional[Union[str, discord.PartialEmoji]]:
    """Retourne un émoji valide pour Discord, sinon None."""
    if val is None:
        return None
    if isinstance(val, discord.PartialEmoji):
        return val
    s = str(val).strip()
    if not s:
        return None
    if s.startswith("<") and s.endswith(">"):
        try:
            return discord.PartialEmoji.from_str(s)
        except Exception:
            return None
    return s if looks_like_unicode_emoji(s) else None


def parse_choice_line(line: str) -> Tuple[Optional[Union[str, discord.PartialEmoji]], str]:
    """
    Parse 'emoji optionnel + espace + libellé'.
    Supporte unicode (🥐) et custom (<:name:id>).
    """
    s = line.strip()
    if not s:
        return None, ""
    if s.startswith("<") and ">" in s:
        maybe = s.split(">", 1)[0] + ">"
        try:
            pe = discord.PartialEmoji.from_str(maybe)
            label = s[len(maybe):].strip()
            return pe, label
        except Exception:
            pass
    parts = s.split(" ", 1)
    if len(parts) == 2:
        first, rest = parts
        if looks_like_unicode_emoji(first):
            return first, rest.strip()
    return None, s

# =========================
#          MODEL
# =========================


@dataclass
class Choice:
    label: str
    emoji: Optional[Union[str, discord.PartialEmoji]] = None


@dataclass
class PollState:
    question: str
    choices: List[Choice]
    author_id: int
    end_time: Optional[datetime]
    channel_id: int
    message_id: Optional[int] = None
    allow_multi: bool = False
    # votes : user -> set d’index si multi, sinon int (index)
    votes_single: Dict[int, int] = field(default_factory=dict)
    votes_multi: Dict[int, set] = field(default_factory=dict)

    @property
    def counts(self) -> List[int]:
        c = [0] * len(self.choices)
        if self.allow_multi:
            for idxs in self.votes_multi.values():
                for i in idxs:
                    if 0 <= i < len(c):
                        c[i] += 1
        else:
            for i in self.votes_single.values():
                if 0 <= i < len(c):
                    c[i] += 1
        return c

    @property
    def total(self) -> int:
        return sum(self.counts)

# =========================
#        VOTE UI
# =========================


class PollButton(discord.ui.Button):
    def __init__(self, index: int, choice: Choice):
        valid_emoji = coerce_emoji(choice.emoji)
        # Discord exige au moins label ou emoji
        label_text = "\u200b" if valid_emoji else (choice.label or "Choix")
        styles = (discord.ButtonStyle.primary,
                  discord.ButtonStyle.secondary, discord.ButtonStyle.success)
        style = styles[index % len(styles)]

        super().__init__(
            style=style,
            label=label_text,
            emoji=valid_emoji,
            row=min(index // 5, 4),
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: PollView = self.view  # type: ignore
        cog: Polls = view.cog
        state: PollState = view.state

        if state.end_time and discord.utils.utcnow() >= state.end_time:
            return await interaction.response.send_message("⏰ Le sondage est déjà terminé.", ephemeral=True)

        uid = interaction.user.id
        changed = False
        if state.allow_multi:
            cur = state.votes_multi.get(uid, set())
            if self.index in cur:
                cur.remove(self.index)   # toggle off
            else:
                cur.add(self.index)      # toggle on
            state.votes_multi[uid] = cur
            changed = True
        else:
            prev = state.votes_single.get(uid)
            state.votes_single[uid] = self.index
            changed = (prev != self.index)

        # MAJ embed
        channel = cog.bot.get_channel(state.channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)) and state.message_id:
            try:
                msg = await channel.fetch_message(state.message_id)
            except discord.HTTPException:
                return
            embed = cog.build_running_embed(state, interaction.user)
            with contextlib.suppress(discord.HTTPException):
                await msg.edit(embed=embed)

        # Feedback
        ch = state.choices[self.index]
        if changed:
            if state.allow_multi:
                sel = sorted(state.votes_multi[uid])
                labels = [state.choices[i].label for i in sel]
                await interaction.response.send_message(
                    f"✅ Sélection mise à jour : {', '.join(labels) if labels else '—'}",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"✅ Vote enregistré pour **{ch.label}**.",
                    ephemeral=True,
                )
        else:
            await interaction.response.send_message("ℹ️ Pas de changement.", ephemeral=True)


class PollView(discord.ui.View):
    def __init__(self, cog: "Polls", state: PollState, *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.state = state
        for i, ch in enumerate(state.choices):
            self.add_item(PollButton(i, ch))

    async def on_timeout(self) -> None:
        # sécurité
        channel = self.cog.bot.get_channel(self.state.channel_id)
        if isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)) and self.state.message_id:
            with contextlib.suppress(Exception):
                msg = await channel.fetch_message(self.state.message_id)
                await self.cog.finalize_poll(msg, self.state)

# =========================
#        WIZARD UI
# =========================


class ChannelPicker(discord.ui.Select):
    """Select simple qui liste jusqu'à 25 salons texte du serveur."""

    def __init__(self, wizard: "PollWizard", guild: discord.Guild, current_channel: Optional[discord.TextChannel]):
        options: List[discord.SelectOption] = []
        texts = sorted([c for c in guild.text_channels],
                       key=lambda c: (c.category_id or 0, c.position))
        for ch in texts[:25]:
            label = f"#{ch.name}"
            desc = ch.category.name if ch.category else "Sans catégorie"
            default = bool(current_channel and (ch.id == current_channel.id))
            options.append(discord.SelectOption(label=label, value=str(
                ch.id), description=desc, default=default))
        super().__init__(placeholder="Choisir le salon (par défaut : ici)",
                         min_values=1, max_values=1, options=options)
        self.wizard = wizard

    async def callback(self, interaction: discord.Interaction):
        try:
            self.wizard.target_channel = int(self.values[0])
        except Exception:
            self.wizard.target_channel = None
        await interaction.response.defer()


class PollWizard(discord.ui.View):
    def __init__(self, cog: "Polls", guild: discord.Guild, current_channel: Optional[discord.TextChannel]):
        super().__init__(timeout=300)
        self.cog = cog
        self.target_channel: Optional[int] = current_channel.id if current_channel else None
        self.allow_multi: bool = False
        self.num_choices: int = 2

        # Sélecteur de salon
        self.add_item(ChannelPicker(self, guild, current_channel))

        # Mode de vote
        self.mode_select = discord.ui.Select(
            placeholder="Mode de vote",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Choix unique", value="single",
                                     emoji="1️⃣", description="1 vote par utilisateur"),
                discord.SelectOption(label="Choix multiples", value="multi",
                                     emoji="✅", description="Plusieurs votes par utilisateur"),
            ],
        )
        self.mode_select.callback = self._on_pick_mode  # type: ignore
        self.add_item(self.mode_select)

        # Nombre de choix
        self.count_select = discord.ui.Select(
            placeholder="Nombre de choix (2–10)",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=str(i), value=str(
                i)) for i in range(2, MAX_CHOICES + 1)],
        )
        self.count_select.callback = self._on_pick_count  # type: ignore
        self.add_item(self.count_select)

        # Continuer
        self.continue_btn = discord.ui.Button(
            label="Continuer ➡️", style=discord.ButtonStyle.success)
        self.continue_btn.callback = self._on_continue  # type: ignore
        self.add_item(self.continue_btn)

    async def _on_pick_mode(self, interaction: discord.Interaction):
        self.allow_multi = (self.mode_select.values[0] == "multi")
        await interaction.response.defer()

    async def _on_pick_count(self, interaction: discord.Interaction):
        self.num_choices = int(self.count_select.values[0])
        await interaction.response.defer()

    async def _on_continue(self, interaction: discord.Interaction):
        channel_id = self.target_channel or (
            interaction.channel.id if interaction.channel else None)
        if channel_id is None:
            return await interaction.response.send_message("⚠️ Impossible de déterminer le salon.", ephemeral=True)
        await interaction.response.send_modal(
            ChoiceModalPart1(self.cog, channel_id,
                             self.allow_multi, self.num_choices)
        )

# =========================
#          MODALS
# =========================


class ChoiceModalPart1(discord.ui.Modal, title="Créer un sondage (1/2)"):
    question = discord.ui.TextInput(
        label="Question", max_length=MAX_QUESTION_LENGTH)
    duree = discord.ui.TextInput(
        label="Durée (minutes, optionnel)", required=False, placeholder="Ex : 60")

    def __init__(self, cog: "Polls", channel_id: int, allow_multi: bool, total_choices: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id
        self.allow_multi = allow_multi
        self.total_choices = total_choices
        self.choice_inputs: List[discord.ui.TextInput] = []
        first_batch = min(5, total_choices)
        for i in range(first_batch):
            ti = discord.ui.TextInput(
                label=f"Choix {i+1}",
                placeholder="Ex : 🥐 Croissant",
                required=True,
                max_length=MAX_CHOICE_LENGTH + 10,  # marge emoji
            )
            self.add_item(ti)
            self.choice_inputs.append(ti)

    async def on_submit(self, interaction: discord.Interaction):
        q = self.question.value.strip()
        if not q:
            return await interaction.response.send_message("⚠️ La question ne peut pas être vide.", ephemeral=True)

        d_minutes: Optional[int] = None
        dv = self.duree.value.strip()
        if dv:
            if not dv.isdigit():
                return await interaction.response.send_message("⚠️ La durée doit être un nombre (minutes).", ephemeral=True)
            d_minutes = int(dv)
            if d_minutes <= 0:
                return await interaction.response.send_message("⚠️ La durée doit être positive.", ephemeral=True)
            if d_minutes > MAX_TIMEOUT_MINUTES:
                return await interaction.response.send_message("⚠️ Durée max : 7 jours (10080).", ephemeral=True)

        collected = [ci.value for ci in self.choice_inputs]
        remaining = self.total_choices - len(collected)

        if remaining > 0:
            await interaction.response.send_modal(
                ChoiceModalPart2(
                    self.cog, self.channel_id, self.allow_multi, q, d_minutes, collected, remaining)
            )
        else:
            await self.cog.create_poll_from_inputs(
                interaction, self.channel_id, self.allow_multi, q, d_minutes, collected
            )


class ChoiceModalPart2(discord.ui.Modal, title="Créer un sondage (2/2)"):
    def __init__(self, cog: "Polls", channel_id: int, allow_multi: bool,
                 question: str, d_minutes: Optional[int], first_lines: List[str], remaining: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.channel_id = channel_id
        self.allow_multi = allow_multi
        self.question = question
        self.d_minutes = d_minutes
        self.first_lines = first_lines
        self.choice_inputs: List[discord.ui.TextInput] = []
        for i in range(remaining):
            ti = discord.ui.TextInput(
                label=f"Choix {len(first_lines)+i+1}",
                placeholder="Ex : 🍫 Pain au chocolat",
                required=True,
                max_length=MAX_CHOICE_LENGTH + 10,
            )
            self.add_item(ti)
            self.choice_inputs.append(ti)

    async def on_submit(self, interaction: discord.Interaction):
        lines = self.first_lines + [ci.value for ci in self.choice_inputs]
        await self.cog.create_poll_from_inputs(
            interaction, self.channel_id, self.allow_multi, self.question, self.d_minutes, lines
        )

# =========================
#            COG
# =========================


class Polls(commands.Cog):
    """Sondages : choix du salon + mode (unique/multiples) + inputs séparés + barres + timer + thème."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sessions: Dict[int, PollState] = {}

    # ------- Création depuis les inputs (emoji optionnel + label) ------- #

    async def create_poll_from_inputs(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        allow_multi: bool,
        question: str,
        d_minutes: Optional[int],
        lines: List[str],
    ):
        if len(lines) < 2:
            return await interaction.response.send_message("⚠️ Mets au moins deux choix.", ephemeral=True)
        if len(lines) > MAX_CHOICES:
            return await interaction.response.send_message(f"⚠️ Maximum {MAX_CHOICES} choix.", ephemeral=True)

        choices: List[Choice] = []
        seen = set()
        for line in lines:
            emoji_raw, label = parse_choice_line(line)
            label = label.strip()
            if not label:
                return await interaction.response.send_message("⚠️ Un des choix est vide.", ephemeral=True)
            if len(label) > MAX_CHOICE_LENGTH:
                return await interaction.response.send_message(
                    f"⚠️ Chaque choix doit faire moins de {MAX_CHOICE_LENGTH} caractères.", ephemeral=True
                )
            key = label.casefold()
            if key in seen:
                return await interaction.response.send_message("⚠️ Choix en double détecté.", ephemeral=True)
            seen.add(key)
            choices.append(Choice(label=label, emoji=coerce_emoji(emoji_raw)))

        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return await interaction.response.send_message("⚠️ Salon invalide.", ephemeral=True)

        if isinstance(channel, discord.abc.GuildChannel):
            me = channel.guild.me
            if me is not None:
                perms = channel.permissions_for(me)
                if not (perms.view_channel and perms.send_messages and perms.embed_links):
                    return await interaction.response.send_message(
                        "⚠️ Il me manque des permissions (voir/envoyer/intégrer).", ephemeral=True
                    )

        end_time = discord.utils.utcnow() + timedelta(minutes=d_minutes) if d_minutes else None
        state = PollState(
            question=question,
            choices=choices,
            author_id=interaction.user.id,
            end_time=end_time,
            channel_id=channel.id,
            allow_multi=allow_multi,
        )

        embed = self.build_running_embed(state, interaction.user)
        view = PollView(self, state, timeout=None)

        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)

        try:
            msg = await channel.send(
                content=f"Sondage proposé par {interaction.user.mention} "
                f"({'choix multiples' if allow_multi else 'choix unique'})",
                embed=embed,
                view=view,
            )
        except discord.HTTPException as exc:
            return await interaction.followup.send(f"⚠️ Impossible de publier le sondage : {exc}", ephemeral=True)

        state.message_id = msg.id
        self._sessions[msg.id] = state

        parts = [f"✅ Sondage publié dans {channel.mention}"]
        if end_time:
            parts.append(
                f"Fin dans {fmt_remaining(int((end_time - discord.utils.utcnow()).total_seconds()))}")
        else:
            parts.append("Durée indéterminée")

        await interaction.followup.send(" • ".join(parts) + f"\n{msg.jump_url}", ephemeral=True)

        if end_time:
            asyncio.create_task(self.run_countdown_and_close(msg, state))

    # ------------------------------ Embeds ------------------------------- #

    def build_running_embed(self, state: PollState, author: discord.abc.User) -> discord.Embed:
        theme = THEMES[ACTIVE_THEME]
        counts = state.counts
        total = sum(counts)

        emb = discord.Embed(
            title=theme["title_running"],
            description=(
                f"**{state.question}**\n\n"
                f"{'Sélection multiple autorisée.' if state.allow_multi else 'Un seul choix par personne.'}"
            ),
            color=theme["color_running"],
        )
        emb.set_author(
            name=getattr(author, "display_name", "Auteur"),
            icon_url=getattr(
                getattr(author, "display_avatar", None), "url", None),
        )
        if theme["banner_url"]:
            emb.set_image(url=theme["banner_url"])

        for ch, c in zip(state.choices, counts):
            pct = (c / total) if total > 0 else 0.0
            bar = make_bar(pct)
            pct_txt = f"{int(round(pct * 100)):>3d}%"
            prefix = f"{ch.emoji} " if ch.emoji else ""
            emb.add_field(
                name=f"{prefix}{ch.label}",
                value=f"`{bar}`  **{c}** vote(s) • `{pct_txt}`",
                inline=False,
            )

        if state.end_time:
            remaining = int(
                (state.end_time - discord.utils.utcnow()).total_seconds())
            emb.set_footer(text=f"Se termine dans {fmt_remaining(remaining)}")
        else:
            emb.set_footer(text="Aucune durée définie")
        return emb

    def build_closed_embed(self, state: PollState, author: discord.abc.User) -> discord.Embed:
        theme = THEMES[ACTIVE_THEME]
        counts = state.counts
        order = sorted(range(len(counts)),
                       key=lambda i: counts[i], reverse=True)
        total = sum(counts)

        emb = discord.Embed(
            title=theme["title_closed"],
            description="Voici les résultats :",
            color=theme["color_closed"],
        )
        emb.set_author(
            name=getattr(author, "display_name", "Auteur"),
            icon_url=getattr(
                getattr(author, "display_avatar", None), "url", None),
        )
        if theme["banner_url"]:
            emb.set_image(url=theme["banner_url"])

        for rank, i in enumerate(order, start=1):
            ch = state.choices[i]
            c = counts[i]
            pct = (c / total) if total > 0 else 0.0
            bar = make_bar(pct)
            pct_txt = f"{int(round(pct * 100)):>3d}%"
            prefix = f"{ch.emoji} " if ch.emoji else ""
            emb.add_field(
                name=f"{medal_for(rank)} {prefix}{ch.label}",
                value=f"`{bar}`  **{c}** vote(s) • `{pct_txt}`",
                inline=False,
            )

        emb.set_footer(text=f"{total} vote(s) • Sondage terminé")
        return emb

    # ---------------------- Countdown & clôture -------------------------- #

    async def run_countdown_and_close(self, message: discord.Message, state: PollState):
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

    # ------------------------------ Commande ----------------------------- #

    @app_commands.command(name="sondage", description="Assistant de création (salon, mode, nombre de choix)")
    async def sondage(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "⚠️ Cette commande doit être utilisée dans un serveur.",
                ephemeral=True,
            )
        current_channel = interaction.channel if isinstance(
            interaction.channel, discord.TextChannel) else None
        await interaction.response.send_message(
            "Configure ton sondage ci-dessous 👇",
            view=PollWizard(self, interaction.guild, current_channel),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
