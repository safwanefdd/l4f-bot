# -*- coding: utf-8 -*-
# config.py
import os
import discord
from discord import Intents

# ─────────────────────────────────────────────────────────
# Token (prend DISCORD_TOKEN si présent, sinon BOT_TOKEN)
# ─────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("DISCORD_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN manquant : définis DISCORD_TOKEN ou BOT_TOKEN dans ton environnement (.env).")

# ─────────────────────────────────────────────────────────
# Intents
# ─────────────────────────────────────────────────────────
INTENTS: Intents = Intents.default()
INTENTS.members = True
INTENTS.voice_states = True
INTENTS.presences = True

# ⚠️ Requis pour la contestation en MP (lire le texte + pièces jointes)
# active aussi dans le Developer Portal (onglet Bot)
INTENTS.message_content = True
INTENTS.dm_messages = True       # réception des DM

# ─────────────────────────────────────────────────────────
# Config serveurs (tes valeurs d’origine conservées)
# ─────────────────────────────────────────────────────────
GUILD_ID = 1424369365595459755
HUB_CHANNEL_ID = 1429891186801381417
CATEGORY_ID = 1429932863389958158
NAME_PREFIX = "🎮 "

# Bienvenue
WELCOME_CHANNEL_ID = 1424372004471046154
WELCOME_ROLE_ID = None
SEND_WELCOME_DM = True
SERVER_RULES_CHANNEL_ID = 1424371734705999993

# ─────────────────────────────────────────────────────────
# Salon de signalement (pour recevoir les contestations)
# ─────────────────────────────────────────────────────────
# Définis SIGNALEMENT_CHANNEL_ID dans ton .env, ex:
# SIGNALEMENT_CHANNEL_ID=123456789012345678
SIGNALEMENT_CHANNEL_ID = int(
    os.getenv("SIGNALEMENT_CHANNEL_ID", "0"))  # 0 = pas configuré
