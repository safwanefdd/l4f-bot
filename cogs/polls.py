import discord
from discord import app_commands
from discord.ext import commands

NUMBER_EMOJIS = (
    "1️⃣",
    "2️⃣",
    "3️⃣",
    "4️⃣",
    "5️⃣",
    "6️⃣",
    "7️⃣",
    "8️⃣",
    "9️⃣",
    "🔟",
)

MAX_QUESTION_LENGTH = 256
MAX_CHOICE_LENGTH = 100


class Polls(commands.Cog):
    """Gestion des sondages via commandes slash."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="sondage", description="Créer un sondage avec réactions pour voter")
    @app_commands.describe(
        question="Intitulé du sondage",
        choix1="Premier choix (obligatoire)",
        choix2="Deuxième choix (obligatoire)",
        choix3="Troisième choix (optionnel)",
        choix4="Quatrième choix (optionnel)",
        choix5="Cinquième choix (optionnel)",
        choix6="Sixième choix (optionnel)",
        choix7="Septième choix (optionnel)",
        choix8="Huitième choix (optionnel)",
        choix9="Neuvième choix (optionnel)",
        choix10="Dixième choix (optionnel)",
    )
    async def sondage(
        self,
        interaction: discord.Interaction,
        question: str,
        choix1: str,
        choix2: str,
        choix3: str | None = None,
        choix4: str | None = None,
        choix5: str | None = None,
        choix6: str | None = None,
        choix7: str | None = None,
        choix8: str | None = None,
        choix9: str | None = None,
        choix10: str | None = None,
    ) -> None:
        # validations avant d'accuser réception
        question = question.strip()
        if not question:
            await interaction.response.send_message(
                "⚠️ La question du sondage ne peut pas être vide.", ephemeral=True
            )
            return
        if len(question) > MAX_QUESTION_LENGTH:
            await interaction.response.send_message(
                f"⚠️ La question doit faire moins de {MAX_QUESTION_LENGTH} caractères.",
                ephemeral=True,
            )
            return

        raw_choices = [choix1, choix2, choix3, choix4, choix5, choix6, choix7, choix8, choix9, choix10]
        cleaned_choices: list[str] = []
        seen_casefold: set[str] = set()
        for choice in raw_choices:
            if choice is None:
                continue
            choice_text = choice.strip()
            if not choice_text:
                continue
            if len(choice_text) > MAX_CHOICE_LENGTH:
                await interaction.response.send_message(
                    f"⚠️ Chaque choix doit faire moins de {MAX_CHOICE_LENGTH} caractères.",
                    ephemeral=True,
                )
                return
            key = choice_text.casefold()
            if key in seen_casefold:
                await interaction.response.send_message(
                    "⚠️ Impossible d'ajouter deux fois le même choix.", ephemeral=True
                )
                return
            seen_casefold.add(key)
            cleaned_choices.append(choice_text)

        if len(cleaned_choices) < 2:
            await interaction.response.send_message(
                "⚠️ Merci de proposer au moins deux choix distincts.", ephemeral=True
            )
            return

        if interaction.channel is None:
            await interaction.response.send_message(
                "⚠️ Impossible de trouver le salon pour publier le sondage.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(title=question, color=discord.Color.blurple())
        description_lines = []
        for emoji, choice_text in zip(NUMBER_EMOJIS, cleaned_choices):
            description_lines.append(f"{emoji} **{choice_text}**")
        embed.description = "\n".join(description_lines)
        embed.set_footer(text=f"Sondage créé par {interaction.user.display_name}")

        try:
            poll_message = await interaction.channel.send(embed=embed)
            for emoji, _ in zip(NUMBER_EMOJIS, cleaned_choices):
                await poll_message.add_reaction(emoji)
        except Exception as exc:  # pragma: no cover - dépend de l'API Discord
            await interaction.followup.send(
                f"⚠️ Impossible de publier le sondage : {exc}", ephemeral=True
            )
            return

        await interaction.followup.send(
            f"✅ Sondage publié avec succès : {poll_message.jump_url}", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
