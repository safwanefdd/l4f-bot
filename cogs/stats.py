# -*- coding: utf-8 -*-
# cogs/stats.py
import os
import sqlite3
from contextlib import closing
from typing import Optional, Iterable, Tuple

import discord
from discord.ext import commands
from discord import app_commands

from config import GUILD_ID

DB_PATH = os.path.join("data", "stats.db")
GUILD_OBJ = discord.Object(id=GUILD_ID) if GUILD_ID else None


def _ensure_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn, conn, closing(conn.cursor()) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS game_stats (
                guild_id   INTEGER NOT NULL,
                member_id  INTEGER NOT NULL,
                game       TEXT    NOT NULL,
                seconds    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, member_id, game)
            )
            """
        )


def _fmt_duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


class StatsCog(commands.Cog):
    """Stats de jeux (stockées dans data/stats.db)"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _ensure_db()

    # --------------------------------------------------------------------- #
    # Utilitaires DB
    # --------------------------------------------------------------------- #
    def _query(
        self, sql: str, args: Iterable = ()
    ) -> list[Tuple]:
        with closing(sqlite3.connect(DB_PATH)) as conn, closing(conn.cursor()) as cur:
            cur.execute(sql, args)
            return cur.fetchall()

    def _exec(self, sql: str, args: Iterable = ()) -> None:
        with closing(sqlite3.connect(DB_PATH)) as conn, conn, closing(conn.cursor()) as cur:
            cur.execute(sql, args)

    # --------------------------------------------------------------------- #
    # Commandes
    # --------------------------------------------------------------------- #

    @app_commands.guilds(GUILD_OBJ)
    @app_commands.command(
        name="top-jeux",
        description="Classement des jeux les plus joués du serveur."
    )
    @app_commands.describe(limite="Nombre de jeux à afficher (défaut 10)")
    async def top_jeux(self, interaction: discord.Interaction, limite: Optional[int] = 10):
        assert interaction.guild, "À utiliser dans une guilde."
        limite = min(25, max(1, int(limite or 10)))

        rows = self._query(
            """
            SELECT game, SUM(seconds) AS total
            FROM game_stats
            WHERE guild_id = ?
            GROUP BY game
            ORDER BY total DESC
            LIMIT ?
            """,
            (interaction.guild.id, limite),
        )

        if not rows:
            return await interaction.response.send_message(
                "Aucune statistique de jeu enregistrée pour ce serveur.", ephemeral=True
            )

        embed = discord.Embed(
            title=f"🏆 Top {len(rows)} jeux — {interaction.guild.name}",
            color=discord.Color.blurple(),
        )
        for i, (game, total) in enumerate(rows, start=1):
            embed.add_field(name=f"{i}. {game}",
                            value=_fmt_duration(total), inline=False)

        await interaction.response.send_message(embed=embed)

    # ----------------------------------------------------------

    @app_commands.guilds(GUILD_OBJ)
    @app_commands.command(
        name="stats-moi",
        description="Tes stats (ou celles d’un membre) par jeu."
    )
    @app_commands.describe(membre="Membre ciblé (défaut: toi)")
    async def stats_moi(self, interaction: discord.Interaction, membre: Optional[discord.Member] = None):
        assert interaction.guild, "À utiliser dans une guilde."
        cible = membre or interaction.user

        rows = self._query(
            """
            SELECT game, seconds
            FROM game_stats
            WHERE guild_id = ? AND member_id = ?
            ORDER BY seconds DESC
            """,
            (interaction.guild.id, cible.id),
        )

        if not rows:
            return await interaction.response.send_message(
                f"Aucune statistique trouvée pour **{cible.display_name}**.", ephemeral=True
            )

        total = sum(sec for _, sec in rows)
        embed = discord.Embed(
            title=f"🎮 Stats — {cible.display_name}",
            description=f"Temps cumulé: **{_fmt_duration(total)}**",
            color=discord.Color.green(),
        )
        for game, sec in rows[:25]:
            embed.add_field(name=game, value=_fmt_duration(sec), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=(cible.id == interaction.user.id))

    # ----------------------------------------------------------

    @app_commands.guilds(GUILD_OBJ)
    @app_commands.command(
        name="stats-jeu",
        description="Top membres pour un jeu donné."
    )
    @app_commands.describe(jeu="Nom du jeu (texte exact)")
    async def stats_jeu(self, interaction: discord.Interaction, jeu: str):
        assert interaction.guild, "À utiliser dans une guilde."

        rows = self._query(
            """
            SELECT member_id, seconds
            FROM game_stats
            WHERE guild_id = ? AND LOWER(game) = LOWER(?)
            ORDER BY seconds DESC
            LIMIT 25
            """,
            (interaction.guild.id, jeu),
        )

        if not rows:
            return await interaction.response.send_message(
                f"Aucun joueur trouvé pour **{jeu}**.", ephemeral=True
            )

        embed = discord.Embed(
            title=f"👥 Top joueurs — {jeu}",
            color=discord.Color.orange(),
        )

        for rank, (mid, sec) in enumerate(rows, start=1):
            member = interaction.guild.get_member(mid)
            name = member.display_name if member else f"Utilisateur {mid}"
            embed.add_field(
                name=f"{rank}. {name}",
                value=_fmt_duration(sec),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    # ----------------------------------------------------------

    @app_commands.guilds(GUILD_OBJ)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.command(
        name="reset-stats",
        description="(Admin) Réinitialise toutes les stats du serveur."
    )
    async def reset_stats(self, interaction: discord.Interaction):
        assert interaction.guild, "À utiliser dans une guilde."
        self._exec("DELETE FROM game_stats WHERE guild_id = ?",
                   (interaction.guild.id,))
        await interaction.response.send_message("🗑️ Stats du serveur **réinitialisées**.", ephemeral=True)

    # --------------------------------------------------------------------- #
    # API interne (facultatif) pour incrémenter les stats depuis d'autres cogs
    # --------------------------------------------------------------------- #
    def add_playtime(self, guild_id: int, member_id: int, game: str, seconds: int) -> None:
        """Incrémente les secondes jouées pour un membre et un jeu."""
        if not game or seconds <= 0:
            return
        with closing(sqlite3.connect(DB_PATH)) as conn, conn, closing(conn.cursor()) as cur:
            cur.execute(
                """
                INSERT INTO game_stats (guild_id, member_id, game, seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, member_id, game)
                DO UPDATE SET seconds = seconds + excluded.seconds
                """,
                (guild_id, member_id, game, int(seconds))
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
