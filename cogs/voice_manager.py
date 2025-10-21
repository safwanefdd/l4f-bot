from discord.ext import commands
import discord
import asyncio
from config import HUB_CHANNEL_ID, CATEGORY_ID, NAME_PREFIX
from cogs.utils import build_channel_name

owner_to_voice = {}
voice_to_owner = {}

class VoiceManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member or member.bot:
            return

        # Rejoint le hub -> création du vocal
        if after.channel and after.channel.id == HUB_CHANNEL_ID:
            guild = member.guild
            category = guild.get_channel(CATEGORY_ID)
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=True, speak=True),
                member: discord.PermissionOverwrite(manage_channels=True)
            }
            new_ch = await guild.create_voice_channel(
                name=build_channel_name(member),
                category=category,
                overwrites=overwrites,
                reason=f"Salon perso pour {member}"
            )
            owner_to_voice[member.id] = new_ch.id
            voice_to_owner[new_ch.id] = member.id
            await asyncio.sleep(0.5)
            await member.move_to(new_ch)
            return

        # Quitte -> supprime si vide
        if before.channel:
            owner_id = voice_to_owner.get(before.channel.id)
            if owner_id is None:
                return

            if len(before.channel.members) == 0:
                await before.channel.delete()
                removed_owner_id = voice_to_owner.pop(before.channel.id, None)
                if removed_owner_id is not None:
                    owner_to_voice.pop(removed_owner_id, None)

async def setup(bot):
    await bot.add_cog(VoiceManager(bot))
