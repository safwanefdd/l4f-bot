import discord
from discord import ActivityType

def build_channel_name(member: discord.Member) -> str:
    """Construit le nom du vocal avec jeu si détecté."""
    display = member.display_name
    game = None
    for act in member.activities:
        if act.type == ActivityType.playing and act.name:
            game = act.name
            break
    return f"🎮 {display} — {game}" if game else f"🎮 {display}"

def control_embed(member: discord.Member, channel: discord.VoiceChannel) -> discord.Embed:
    """Construit l'embed principal du panneau."""
    e = discord.Embed(
        title="🎛️ Panneau de contrôle",
        description=f"Salon : **{channel.name}**\nUtilise les boutons ci-dessous pour le gérer.",
        colour=discord.Colour.blurple()
    )
    e.set_author(name=member.display_name, icon_url=member.display_avatar)
    e.set_footer(text="Astuce : change de jeu et le nom s’adaptera tout seul ✨")
    return e

def fmt_short_duration(seconds: int) -> str:
    m, s = divmod(max(0, seconds), 60)
    h, m = divmod(m, 60)
    if h: return f"{h} h {m} min"
    if m: return f"{m} min"
    return f"{s} s"
