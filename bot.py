# bot.py
import logging
import discord
from discord.ext import commands
from config import BOT_TOKEN, INTENTS, GUILD_ID  # <- mets ton GUILD_ID dans config.py

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

INITIAL_EXTENSIONS = [
    "cogs.voice_manager",
    "cogs.panel",
    "cogs.welcome",
    "cogs.stats",
    "cogs.polls",
    "cogs.admin",
    "cogs.reaction_roles_wizard",
]

class MyBot(commands.Bot):
    async def setup_hook(self):
        # charge tous les cogs
        for ext in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(ext)
                print(f"📦 Chargé : {ext}")
            except Exception as e:
                print(f"⚠️ Erreur chargement {ext}: {e}")

        # SYNC des slash commands (immédiate si guild spécifié)
        try:
            if GUILD_ID:
                guild = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild)  # optionnel
                await self.tree.sync(guild=guild)      # ⭐ instantané sur ce serveur
                print(f"✅ Slash commands synchronisées sur guild {GUILD_ID}")
            else:
                await self.tree.sync()                 # global (peut prendre du temps)
                print("✅ Slash commands synchronisées (global)")
        except Exception as e:
            print(f"⚠️ Sync slash échouée: {e}")

bot = MyBot(command_prefix="!", intents=INTENTS, allowed_mentions=None)

@bot.event
async def on_ready():
    print(f"🚀 Connecté comme {bot.user} ({bot.user.id})")

if __name__ == "__main__":
    if not BOT_TOKEN:
        raise SystemExit("⚠️ BOT_TOKEN manquant.")
    bot.run(BOT_TOKEN)
