# -*- coding: utf-8 -*-
# bot.py
import logging
import sys
import discord
from discord.ext import commands

from config import (
    BOT_TOKEN,
    INTENTS,
    GUILD_ID,
)

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("bot")

# ─────────────────────────────────────────────────────────
# Cogs à charger
# ─────────────────────────────────────────────────────────
INITIAL_EXTENSIONS: list[str] = [
    "cogs.voice_manager",
    "cogs.panel",
    "cogs.welcome",
    "cogs.stats",
    "cogs.polls",
    "cogs.admin",
    "cogs.reaction_roles_wizard",
    "cogs.invite",
    "cogs.moderation",
    "cogs.sync",
]

# ─────────────────────────────────────────────────────────
# Bot class
# ─────────────────────────────────────────────────────────


class MyBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            # évite @everyone/@here accidentels
            allowed_mentions=discord.AllowedMentions.none(),
            # (optionnel) on masque le help texte si tu as un /help
            help_command=None,
        )

# bot.py (dans MyBot)


async def setup_hook(self) -> None:
    # 1) Charge les cogs
    for ext in INITIAL_EXTENSIONS:
        try:
            await self.load_extension(ext)
            log.info(f"📦 Chargé : {ext}")
        except Exception:
            log.exception(f"⚠️ Erreur chargement {ext}")

    # 2) Resync forcé sur ta guilde et LOG des commandes vues par Discord
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            # on nettoie puis on resynchronise
            self.tree.clear_commands(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info(
                f"✅ Resync guild {GUILD_ID} → {len(synced)} commandes : {[c.name for c in synced]}")
            # (optionnel) purge globale pour éviter des doublons fantômes
            # self.tree.clear_commands() ; await self.tree.sync()
        else:
            synced = await self.tree.sync()
            log.info(
                f"🌍 Resync global → {len(synced)} commandes : {[c.name for c in synced]}")
    except Exception:
        log.exception("⚠️ Échec de synchronisation des slash")

    async def on_ready(self) -> None:
        u = self.user
        if u is None:
            return
        log.info(
            "🚀 Connecté comme %s (%s) • guilds=%d • intents.message_content=%s",
            u, u.id, len(self.guilds), self.intents.message_content
        )

# ─────────────────────────────────────────────────────────
# Entrée
# ─────────────────────────────────────────────────────────


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "❌ BOT_TOKEN manquant (définis DISCORD_TOKEN ou BOT_TOKEN dans ton environnement).")
    bot = MyBot()
    # On laisse discord.py gérer ses propres logs via notre config
    bot.run(BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
