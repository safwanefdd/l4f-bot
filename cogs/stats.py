# cogs/stats.py
import os
import sqlite3
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

import discord
from discord.ext import commands, tasks
from discord import app_commands, ActivityType

from config import GUILD_ID


DB_PATH = os.path.join("data", "stats.db")

logger = logging.getLogger(__name__)

# En mémoire: début de session par (guild_id, user_id) -> nom du jeu
active_sessions: Dict[int, Dict[int, tuple[str, datetime]]] = {}


def ensure_db():
    os.makedirs("data", exist_ok=True)
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        # table des cumuls (par serveur, jeu, user) en secondes
        cur.execute("""
        CREATE TABLE IF NOT EXISTS playtime (
            guild_id INTEGER NOT NULL,
            user_id  INTEGER NOT NULL,
            game     TEXT    NOT NULL,
            seconds  INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id, game)
        )
        """)
        # vue/indice utile
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_playtime_guild_game ON playtime (guild_id, game)")
        con.commit()


def add_seconds(guild_id: int, user_id: int, game: str, seconds: int):
    if seconds <= 0:
        return
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO playtime (guild_id, user_id, game, seconds)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id, game)
            DO UPDATE SET seconds = seconds + excluded.seconds
        """, (guild_id, user_id, game, seconds))
        con.commit()


def fmt_dur(seconds: int) -> str:
    # format court lisible (h mn)
    m, s = divmod(max(0, seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h} h {m} min"
    if m > 0:
        return f"{m} min"
    return f"{s} s"


class Stats(commands.Cog):
    """Stats de jeux: enregistre le temps par jeu via l'activité Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ensure_db()
        self.autosave.start()

    def cog_unload(self):
        self.autosave.cancel()

    # --- Tâche de sauvegarde de sécurité (si une session reste ouverte) ---
    @tasks.loop(minutes=2)
    async def autosave(self):
        # rien à faire ici car on sauvegarde à la fermeture de session
        # mais on pourrait forcer un flush si on passait par un cache en mémoire
        pass

    # --- Présence: ouvrir/fermer des sessions ---
    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        # On ne traque que les humains
        if after.bot or not after.guild:
            return

        # détecter le jeu "playing"
        def get_game(member: discord.Member) -> Optional[str]:
            if member.activities:
                for act in member.activities:
                    if act.type == ActivityType.playing and act.name:
                        return act.name.strip()[:100]
            return None

        user_id = after.id
        guild_id = after.guild.id
        now = datetime.now(timezone.utc)

        before_game = get_game(before) if isinstance(
            before, discord.Member) else None
        after_game = get_game(after)

        # cas 1: même jeu -> rien
        if before_game == after_game:
            return

        # cas 2: fermeture de l'ancienne session
        guild_sessions = active_sessions.get(guild_id)
        if guild_sessions and user_id in guild_sessions:
            old_game, started_at = guild_sessions.pop(user_id)
            delta = int((now - started_at).total_seconds())
            if delta > 0:
                add_seconds(guild_id, user_id, old_game, delta)
            logger.debug(
                "Session fermée", extra={
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "game": old_game,
                    "duration": delta,
                }
            )
            if not guild_sessions:
                active_sessions.pop(guild_id, None)

        # cas 3: ouverture de la nouvelle session
        if after_game:
            guild_sessions = active_sessions.setdefault(guild_id, {})
            guild_sessions[user_id] = (after_game, now)
            logger.debug(
                "Session ouverte", extra={
                    "guild_id": guild_id,
                    "user_id": user_id,
                    "game": after_game,
                    "started_at": now.isoformat(),
                }
            )

    # --- Commandes slash ---
    @app_commands.command(name="top-jeux", description="Classement des jeux les plus joués du serveur")
    async def top_jeux(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 20] = 10):
        await interaction.response.defer(ephemeral=True)
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            cur.execute("""
                SELECT game, SUM(seconds) as total
                FROM playtime
                WHERE guild_id = ?
                GROUP BY game
                ORDER BY total DESC
                LIMIT ?
            """, (interaction.guild_id, limit))
            rows = cur.fetchall()

        if not rows:
            await interaction.followup.send("Aucune donnée pour l’instant. Lancez un jeu 🎮", ephemeral=True)
            return

        desc = "\n".join(
            f"**{i+1}.** {game} — {fmt_dur(sec)}"
            for i, (game, sec) in enumerate(rows)
        )
        embed = discord.Embed(
            title="🏆 Top jeux du serveur",
            description=desc,
            colour=discord.Colour.gold()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="stats-moi", description="Tes stats de jeu (temps cumulé par jeu)")
    async def stats_moi(self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 20] = 10):
        await interaction.response.defer(ephemeral=True)
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            cur.execute("""
                SELECT game, seconds
                FROM playtime
                WHERE guild_id = ? AND user_id = ?
                ORDER BY seconds DESC
                LIMIT ?
            """, (interaction.guild_id, interaction.user.id, limit))
            rows = cur.fetchall()

        # additionne la session en cours (si jeu actif)
        add_line = ""
        guild_sessions = active_sessions.get(interaction.guild_id, {})
        session = guild_sessions.get(interaction.user.id)
        if session:
            g, started = session
            extra = int((datetime.now(timezone.utc) - started).total_seconds())
            if extra > 5:
                add_line = f"\n*(en cours)* **{g}** +{fmt_dur(extra)}"

        if not rows and not add_line:
            await interaction.followup.send("Pas encore de stats pour toi. Lance un jeu 🎮", ephemeral=True)
            return

        desc = "\n".join(
            f"• **{game}** — {fmt_dur(sec)}" for game, sec in rows) + add_line
        embed = discord.Embed(
            title=f"📊 Stats de {interaction.user.display_name}",
            description=desc.strip(),
            colour=discord.Colour.blurple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="stats-jeu", description="Détails pour un jeu précis (serveur)")
    async def stats_jeu(self, interaction: discord.Interaction, nom: str):
        await interaction.response.defer(ephemeral=True)
        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            cur.execute("""
                SELECT user_id, seconds
                FROM playtime
                WHERE guild_id = ? AND game = ?
                ORDER BY seconds DESC
                LIMIT 20
            """, (interaction.guild_id, nom))
            rows = cur.fetchall()

        if not rows:
            await interaction.followup.send(f"Aucune donnée pour **{nom}**.", ephemeral=True)
            return

        lines = []
        for i, (uid, sec) in enumerate(rows, start=1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"Utilisateur {uid}"
            lines.append(f"**{i}.** {name} — {fmt_dur(sec)}")

        embed = discord.Embed(
            title=f"🎮 Stats — {nom}",
            description="\n".join(lines),
            colour=discord.Colour.green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="reset-stats", description="(Admin) Réinitialiser toutes les stats du serveur")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.command(name="reset-stats", description="(Admin) Réinitialiser toutes les stats du serveur")
    async def reset_stats(self, interaction: discord.Interaction, confirmation: bool):
        if not confirmation:
            await interaction.response.send_message("❌ Annulé. Passe `confirmation: true` pour confirmer.", ephemeral=True)
            return

        with sqlite3.connect(DB_PATH) as con:
            cur = con.cursor()
            cur.execute("DELETE FROM playtime WHERE guild_id = ?",
                        (interaction.guild_id,))
            con.commit()

        # on vide les sessions en cours des membres de ce serveur
        guild_sessions = active_sessions.pop(interaction.guild_id, None)
        if guild_sessions:
            logger.debug(
                "Sessions purgées", extra={
                    "guild_id": interaction.guild_id,
                    "count": len(guild_sessions),
                }
            )

        await interaction.response.send_message("🗑️ Stats réinitialisées pour ce serveur.", ephemeral=True)

    # S'assurer que les commandes sont visibles rapidement
    async def cog_load(self):
        try:
            await self.bot.tree.sync()
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
