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

    async def setup_hook(self) -> None:
        # 1) Charger les cogs
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                log.info(f"📦 Chargé : {ext}")
            except Exception:
                log.exception(f"⚠️ Erreur chargement {ext}")

        # 2) Sync des slash commands
        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                # Si tu veux dupliquer des globales vers la guilde, décommente la ligne suivante :
                # self.tree.copy_global_to(guild=guild_obj)
                # ⭐ instantané sur ta guilde
                await self.tree.sync(guild=guild_obj)
                log.info(
                    f"✅ Slash commands synchronisées sur guild {GUILD_ID}")
            else:
                await self.tree.sync()  # Global (peut mettre jusqu’à ~1h la 1re fois)
                log.info("✅ Slash commands synchronisées (global)")
        except Exception:
            log.exception("⚠️ Échec de synchronisation des slash commands")

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
