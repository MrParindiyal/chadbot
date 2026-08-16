import asyncio
import copy
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.helpers import *
import time

logger = logging.getLogger(__name__)


class Wordy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="wordy", description="Start a game of Wordy")
    @app_commands.describe(image_mode="Substitue keyboard with an image")
    async def wordy(self, interaction: discord.Interaction, image_mode: bool = False):
        if self.bot.wordy_active:
            await interaction.response.send_message(
                ":x: A Wordy game is already ongoing! Please wait for it to finish or end it.",
                ephemeral=True,
            )
            return

        target_word = pick_random_word()

        self.bot.wordy_active = True
        self.bot.wordy_word = target_word
        self.bot.wordy_guesses = []
        self.bot.wordy_author = interaction.user
        self.bot.explored = copy.deepcopy(KEYBOARD)

        self.bot.unix_end_timer = int(time.time() + WORDY_TIMER)
        initial_embed = create_wordy_embed(
            [],
            target_word,
            self.bot.explored,
            interaction.user,
            self.bot.unix_end_timer,
        )
        view = WordyEndButton(self.bot, interaction.user)

        await interaction.response.send_message(embed=initial_embed, view=view)
        self.bot.wordy_message = await interaction.original_response()

        self.bot.wordy_timer_task = asyncio.create_task(
            background_timer_task(self.bot, WORDY_TIMER)
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
                is_game_over = is_winner or (len(self.bot.wordy_guesses) >= 6)

                updated_embed = create_wordy_embed(
                    self.bot.wordy_guesses,
                    self.bot.wordy_word,
                    self.bot.explored,
                    message.author,
                    self.bot.unix_end_timer,
                    game_over=is_game_over,
                )

                view = discord.ui.View()
                if is_winner:
                    updated_embed.color = discord.Color.green()
                    updated_embed.set_footer(
                        text=f"🎉 Won by {message.author.display_name}! The word was {self.bot.wordy_word.upper()}."
                    )

                elif len(self.bot.wordy_guesses) >= 6:
                    updated_embed.color = discord.Color.red()
                    updated_embed.set_footer(
                        text=f"💀 Game Over! The word was {self.bot.wordy_word.upper()}."
                    )

                else:
                    view = WordyEndButton(self.bot, self.bot.wordy_author)

                try:
                    await self.bot.wordy_message.edit(
                        embed=updated_embed, view=view if not is_game_over else None
                    )
                except AttributeError as e:
                    logger.warning(f"Message not found : {e}")
                if is_game_over:
                    if self.bot.wordy_timer_task:
                        self.bot.wordy_timer_task.cancel()
                        self.bot.wordy_timer_task = None
                    flush_game_data(self.bot)


async def setup(bot):
    await bot.add_cog(Wordy(bot))
