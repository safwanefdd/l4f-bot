# cogs/__init__.py
import importlib
import os

def load_all_cogs(bot):
    """Charge tous les COGs du dossier automatiquement"""
    for filename in os.listdir(os.path.dirname(__file__)):
        if filename.endswith(".py") and not filename.startswith("__"):
            module = f"cogs.{filename[:-3]}"
            try:
                bot.load_extension(module)
                print(f"📦 Chargé : {module}")
            except Exception as e:
                print(f"⚠️ Erreur chargement {module}: {e}")
