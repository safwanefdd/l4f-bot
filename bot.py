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

# bot.py — remplace la classe par ce bloc


class MyBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            allowed_mentions=discord.AllowedMentions.none(),
            help_command=None,
        )
        self.log = logging.getLogger("bot")

    async def setup_hook(self) -> None:
        # 1) Charger les cogs
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                self.log.info(f"📦 Chargé : {ext}")
            except Exception:
                self.log.exception(f"⚠️ Erreur chargement {ext}")

        # 2) Sync GUILDE (et optionnellement global pour rattraper les non-scopées)
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                synced_g = await self.tree.sync(guild=guild)
                self.log.info(
                    f"✅ Sync guild {GUILD_ID} → {len(synced_g)} : {[c.name for c in synced_g]}")
            # (facultatif mais pratique) on tente aussi une sync globale pour les cmd sans @guilds
            synced = await self.tree.sync()
            self.log.info(
                f"🌍 Sync global → {len(synced)} : {[c.name for c in synced]}")
        except Exception:
            self.log.exception("⚠️ Échec de synchronisation des slash")

    async def on_ready(self) -> None:
        u = self.user
        if u:
            self.log.info(
                "🚀 Connecté comme %s (%s) • guilds=%d • intents.message_content=%s",
                u, u.id, len(self.guilds), self.intents.message_content
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
            # ❌ ne PAS faire: self.tree.clear_commands(guild=guild)
            synced = await self.tree.sync(guild=guild)   # ← suffit
            names = [c.name for c in synced]
            log.info(
                f"✅ Sync guild {GUILD_ID} → {len(synced)} commandes : {names}")
        else:
            synced = await self.tree.sync()
            names = [c.name for c in synced]
            log.info(f"🌍 Sync global → {len(synced)} commandes : {names}")
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
