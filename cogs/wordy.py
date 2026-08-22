from __future__ import annotations
import asyncio
import copy
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.helpers import *
import time
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
        difficulty = timer_difficulty.value if timer_difficulty else "medium"
        if self.bot.wordy_active:
            await interaction.response.send_message(
                ":x: A Wordy game is already ongoing! Please wait for it to finish or end it.",
                ephemeral=True,
            )
            return

        self.bot.wordy_active = True
        self.bot.wordy_word = pick_random_word()
        self.bot.wordy_guesses = []
        self.bot.wordy_author = interaction.user
        self.bot.explored = copy.deepcopy(KEYBOARD)
        self.bot.unix_end_timer = int(time.time() + WORDY_TIMER[difficulty])
        self.bot.difficulty = difficulty

        initial_embed = create_wordy_embed(
            [],
            self.bot.wordy_word,
            self.bot.difficulty,
            self.bot.explored,
            interaction.user,
            self.bot.unix_end_timer,
        )
        view = WordyEndButton(self.bot, interaction.user)

        await interaction.response.send_message(embed=initial_embed, view=view)
        self.bot.wordy_message = await interaction.original_response()

        self.bot.wordy_timer_task = asyncio.create_task(
            background_timer_task(self.bot, WORDY_TIMER[difficulty])
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        if self.bot.wordy_active and message.author.id == self.bot.wordy_author.id:
            content = message.content.strip()

            if (
                content.isalpha()
                and not content.startswith("!")
                and self.bot.wordy_active
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
                        delete_after=5,
                    )
                    await self.bot.process_commands(message)
                    return

                guess = content.lower()
                if guess not in ALLOWED_GUESSES:
                    await message.delete(delay=3)
                    await message.channel.send(
                        f"{message.author.mention} :warning: Not a valid guess.",
                        delete_after=2.5,
                    )
                    return
                try:
                    await message.delete(delay=1.8)
                except discord.Forbidden as e:
                    logger.warning(
                        f"Message deletion failed: {e.status} {e.text} : {e.response}"
                    )

                self.bot.wordy_guesses.append(guess)

                is_winner = guess == self.bot.wordy_word
                guess_exhausted = len(self.bot.wordy_guesses) >= 6

                if is_winner:
                    await end_game_helper(
                        self.bot, interaction=None, timed_out=False, is_winner=True
                    )
                    return
                elif guess_exhausted:
                    await end_game_helper(
                        self.bot, interaction=None, timed_out=False, is_winner=False
                    )

                updated_embed = create_wordy_embed(
                    self.bot.wordy_guesses,
                    self.bot.wordy_word,
                    self.bot.difficulty,
                    self.bot.explored,
                    message.author,
                    self.bot.unix_end_timer,
                )

                view = WordyEndButton(self.bot, self.bot.wordy_author)

                try:
                    await self.bot.wordy_message.edit(embed=updated_embed, view=view)
                except discord.HTTPException as e:
                    logger.warning(f"Issue with embeds", exc_info=e)
                except AttributeError as e:
                    logger.warning(f"Message not found : {e}")


async def setup(bot: CustomBot):
    await bot.add_cog(Wordy(bot))
