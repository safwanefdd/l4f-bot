# -*- coding: utf-8 -*-
# cogs/reaction_roles_wizard.py
import asyncio
import os
import json
import re
import discord
from discord.ext import commands
from discord import app_commands
from config import GUILD_ID

DB_PATH = os.path.join("data", "reaction_roles.json")

# ---------------- DB ----------------


def ensure_db():
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(DB_PATH):
        with open(DB_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f)


def load_db():
    ensure_db()
    with open(DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_db(db):
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


# ------------- EMOJI UTILS -------------
EMOJI_REGEX = re.compile(r"<a?:\w+:\d+>")


def to_partial_emoji(s: str) -> discord.PartialEmoji | str:
    s = s.strip()
    if EMOJI_REGEX.fullmatch(s):
        return discord.PartialEmoji.from_str(s)
    return s


def sanitize_unicode_emoji(s: str) -> str:
    INVIS = "\uFE0F\uFE0E\u200D\u200C\u200B\u2060\u00A0"
    return "".join(ch for ch in s if ch not in INVIS).strip()


def emoji_from_role_name(name: str) -> str | None:
    if not name:
        return None
    head = name.strip().split()[0]
    head = head.strip("・-:|~•·")
    if all(ch.isalnum() or ch in "_-" for ch in head):
        return None
    return head or None


async def pretest_emojis(bot: commands.Bot, channel: discord.TextChannel,
                         emoji_list: list[discord.PartialEmoji | str]) -> tuple[bool, list[str]]:
    perms = channel.permissions_for(channel.guild.me)
    if not perms.add_reactions or not perms.read_message_history:
        return False, ["Le bot n’a pas la permission **Ajouter des réactions** et/ou **Lire l’historique**."]

    tmp = await channel.send("⏳ Vérification des émojis… (message auto-supprimé)")
    errors = []
    for e in emoji_list:
        try:
            await tmp.add_reaction(e)
            await asyncio.sleep(0.15)
        except Exception as err:
            errors.append(f"{e} → {err}")
    try:
        await tmp.delete()
    except Exception:
        pass
    return (len(errors) == 0, errors)

# ------------- VIEW -------------


class RolePickView(discord.ui.View):
    def __init__(self, author_id: int, channel: discord.TextChannel, title: str, desc: str | None):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.channel = channel
        self.title = title
        self.desc = desc or ""
        self.role_select = discord.ui.RoleSelect(
            placeholder="Choisis 1 à 20 rôles…", min_values=1, max_values=20)
        self.add_item(self.role_select)

    @discord.ui.button(label="Continuer ➡️", style=discord.ButtonStyle.success, custom_id="rr:auto-continue")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ Ce panneau ne t’appartient pas.", ephemeral=True)

        roles = list(self.role_select.values or [])
        if not roles:
            return await interaction.response.send_message("❌ Sélectionne au moins un rôle.", ephemeral=True)

        mapping: dict[str, int] = {}
        lines: list[str] = []
        emoji_for_react: list[discord.PartialEmoji | str] = []
        perms = self.channel.permissions_for(self.channel.guild.me)

        for role in roles:
            emj_raw = emoji_from_role_name(role.name)
            if not emj_raw:
                return await interaction.response.send_message(
                    f"❌ Le rôle **{role.name}** n’a pas d’emoji en tête. Renomme-le ex. `⚽ FIFA`.",
                    ephemeral=True
                )

            obj = to_partial_emoji(emj_raw)
            if isinstance(obj, discord.PartialEmoji) and obj.id:
                if not perms.external_emojis and not self.channel.guild.get_emoji(obj.id):
                    return await interaction.response.send_message(
                        f"❌ L’emoji **{emj_raw}** est un emoji *custom* externe.",
                        ephemeral=True
                    )
                key = str(obj)
                react_item = obj
            else:
                uni = sanitize_unicode_emoji(str(obj))
                key = uni
                react_item = uni

            if key in mapping:
                return await interaction.response.send_message(
                    f"❌ L’emoji **{emj_raw}** est utilisé plusieurs fois.",
                    ephemeral=True
                )

            mapping[key] = role.id
            emoji_for_react.append(react_item)
            lines.append(f"{emj_raw}  →  {role.mention}")

        ok, errs = await pretest_emojis(interaction.client, self.channel, emoji_for_react)
        if not ok:
            bullet = "\n".join(f"• {e}" for e in errs[:10])
            return await interaction.response.send_message(
                "❌ Certains émojis ne fonctionnent pas :\n" + bullet,
                ephemeral=True
            )

        embed = discord.Embed(
            title=self.title, description=self.desc, colour=discord.Colour.blurple())
        embed.add_field(name="Réagis pour obtenir le rôle :",
                        value="\n".join(lines), inline=False)

        msg = await self.channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        for e in emoji_for_react:
            try:
                await msg.add_reaction(e)
            except Exception:
                await msg.add_reaction(str(e))
            await asyncio.sleep(0.2)

        db = load_db()
        db[str(msg.id)] = {"guild_id": interaction.guild_id, "map": mapping}
        save_db(db)

        await interaction.response.send_message(
            f"✅ Reaction Roles créé dans {self.channel.mention} (ID `{msg.id}`)", ephemeral=True
        )
        self.stop()

# ------------- COG -------------


class ReactionRolesWizard(commands.Cog):
    """Assistant Reaction Roles."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ensure_db()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        entry = load_db().get(str(payload.message_id))
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role_id = entry["map"].get(str(payload.emoji))
        if not role_id:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.add_roles(role, reason="Reaction Roles: add")
            except:
                pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        entry = load_db().get(str(payload.message_id))
        if not entry:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role_id = entry["map"].get(str(payload.emoji))
        if not role_id:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction Roles: remove")
            except:
                pass

    @app_commands.guilds(discord.Object(id=GUILD_ID))
    @app_commands.command(
        name="creer-rr",
        description="Créer un Reaction Roles à partir des rôles (emoji lu au début du nom)."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        canal="Salon où publier le message",
        titre="Titre de l’embed (ex: Choisis tes jeux)",
        description="Texte sous le titre (optionnel)"
    )
    async def creer_rr(self, interaction: discord.Interaction,
                       canal: discord.TextChannel, titre: str, description: str | None = None):
        view = RolePickView(interaction.user.id, canal,
                            titre, description or "")
        await interaction.response.send_message(
            "Sélectionne les **rôles** à associer puis clique **Continuer**.",
            view=view, ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRolesWizard(bot))
