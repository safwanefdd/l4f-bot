# -*- coding: utf-8 -*-
# config.py
import os
import logging
import discord
from dotenv import load_dotenv

# Charge .env si présent (DISCORD_TOKEN, GUILD_ID, etc.)
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Token & IDs
# ──────────────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN manquant (définis DISCORD_TOKEN ou BOT_TOKEN dans ton environnement)")


def _parse_int(name: str) -> int | None:
    raw = os.getenv(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"❌ {name} n’est pas un entier valide : {raw!r}")


# pour sync instantanée des slash
GUILD_ID: int | None = _parse_int("GUILD_ID")
OWNER_ID: int | None = _parse_int("OWNER_ID")     # (optionnel)

# Salon SIGNALEMENT lu directement par le cog moderation via os.getenv("SIGNALEMENT_CHANNEL_ID")

# ──────────────────────────────────────────────────────────────────────────────
# Intents
# ──────────────────────────────────────────────────────────────────────────────
INTENTS = discord.Intents.default()
INTENTS.guilds = True
# utile si tu manipules les rôles / welcome / stats
INTENTS.members = True
# nécessaire pour lire le contenu des MP (contestation)
INTENTS.message_content = True
INTENTS.dm_messages = True             # DM pour recevoir la contestation

# ⚠️ Pense à activer "MESSAGE CONTENT INTENT" dans le Developer Portal si ce n’est pas déjà le cas.

# ──────────────────────────────────────────────────────────────────────────────
# Logs
# ──────────────────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="[%(levelname)s] %(name)s: %(message)s"
)

# ──────────────────────────────────────────────────────────────────────────────
# Extensions (cogs) à charger
# ──────────────────────────────────────────────────────────────────────────────
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
