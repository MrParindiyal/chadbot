from __future__ import annotations
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.config import ALLOWED_GUESSES, WORDY_TIMER
from src.wordy import (
    WordyEndButton,
    WordyGame,
    background_timer_task,
    create_wordy_embed,
    end_game_helper,
)
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from main import CustomBot


class Wordy(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot

    @app_commands.command(name="wordy", description="Start a game of Wordy")
    @app_commands.describe(
        timer_difficulty="Set timer for game",
        image_mode="Substitue keyboard with an image",
    )
    @app_commands.choices(
        timer_difficulty=[
            app_commands.Choice(name="Easy (5 min)", value="easy"),
            app_commands.Choice(name="Medium (3 min)", value="medium"),
            app_commands.Choice(name="Hard (1.5 min)", value="hard"),
        ]
    )
    async def wordy(
        self,
        interaction: discord.Interaction,
        timer_difficulty: app_commands.Choice[str] = None,
        image_mode: bool = False,
    ):
        if self.bot.wordy_games.get(interaction.user.id) != None:
            await interaction.response.send_message(
                ":x: A Wordy game is already ongoing! Please wait for it to finish or end it.",
                ephemeral=True,
            )
            return

        channel = interaction.channel

        if isinstance(channel, discord.PartialMessageable):
            channel = await interaction.guild.fetch_channel(channel.id)

        if isinstance(channel, discord.Thread):
            await interaction.response.send_message(
                ":x: Cannot start new game inside a thread!", ephemeral=True
            )
            return

        difficulty = timer_difficulty.value if timer_difficulty else "medium"
        game = WordyGame(self.bot, interaction, difficulty)
        self.bot.wordy_games[interaction.user.id] = game

        initial_embed = create_wordy_embed(
            [],
            game.wordy_word,
            game.difficulty,
            game.explored,
            interaction.user,
            game.unix_end_timer,
        )

        view = WordyEndButton(game)

        await interaction.response.send_message(embed=initial_embed, view=view)
        game.wordy_message = await interaction.original_response()
        thread = await game.wordy_message.create_thread(
            name=f"Wordy game for {game.player.display_name}", reason="WordyGameThread"
        )
        game.threadid = game.wordy_message.id
        message = await thread.send(f"{game.player.mention}")
        await message.edit(content="Send your guesses here")

        game.wordy_timer_task = asyncio.create_task(
            background_timer_task(game, WORDY_TIMER[difficulty])
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.bot.wordy_games.get(message.author.id) != None:
            content = message.content.strip()
            game = self.bot.wordy_games.get(message.author.id)

            if (
                content.isalpha()
                and not content.startswith("!")
                and message.channel.id == game.threadid
            ):

                if len(content) != 5:
                    try:
                        await message.delete()
                    except discord.HTTPException as e:
                        logger.warning(
                            f"Error while deleting guess : {e.status} {e.text} : {e.response}"
                        )
                    await message.channel.send(
                        f"{message.author.mention} :warning: Game is ongoing. This word does not qualify as a guess (must be exactly 5 letters).",
                        delete_after=6,
                    )
                    return

                guess = content.lower()
                if guess not in ALLOWED_GUESSES:
                    await message.delete(delay=3)
                    await message.channel.send(
                        f"{message.author.mention} :warning: Not a valid guess.",
                        delete_after=2.5,
                    )
                    return

                game.wordy_guesses.append(guess)

                is_winner = guess == game.wordy_word
                guess_exhausted = len(game.wordy_guesses) >= 6

                if is_winner:
                    await end_game_helper(
                        game, interaction=None, timed_out=False, is_winner=True
                    )
                    return
                elif guess_exhausted:
                    await end_game_helper(
                        game, interaction=None, timed_out=False, is_winner=False
                    )
                    return

                updated_embed = create_wordy_embed(
                    game.wordy_guesses,
                    game.wordy_word,
                    game.difficulty,
                    game.explored,
                    message.author,
                    game.unix_end_timer,
                )

                view = WordyEndButton(game)

                try:
                    await game.wordy_message.edit(embed=updated_embed, view=view)
                except discord.HTTPException as e:
                    logger.warning(f"Issue with embeds", exc_info=e)
                except AttributeError as e:
                    logger.warning(f"Message not found : {e}")


async def setup(bot: CustomBot):
    await bot.add_cog(Wordy(bot))
