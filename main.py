from dotenv import load_dotenv

import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from src.gemini import generative_response
import os
from src.helpers import *
from src.response import random_response, hook
from webserver import keep_alive

load_dotenv()


class CustomBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.messages = True
        game_activity = discord.Game(name="with your Mom 😇")

        super().__init__(
            command_prefix="!",
            case_insensitive=True,
            intents=intents,
            activity=game_activity,
            status=discord.Status.online,
        )

        self.wordle_active = False
        self.wordle_word = ""
        self.wordle_guesses = []
        self.wordle_message = None
        self.wordle_author = None

    async def setup_hook(self):
        await self.tree.sync()


bot = CustomBot()


@bot.event
async def on_ready():
    print(f"We have logged in successfully as {bot.user}")


@bot.tree.command(name="ping", description="Returns the bot's gateway latency")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000, 2)
    await interaction.response.send_message(f"pong! ({latency_ms} ms)")


@bot.tree.command(
    name="whitelist", description="Add a user to bot's approve list [admin only]"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def whitelist(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    success = whitelist_user(str(user.id))

    if success:
        await interaction.followup.send(
            f":white_check_mark: Successfully added **{user.name}** to the approved whitelist.",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            f":warning: **{user.name}** is already on the whitelist.", ephemeral=True
        )


@whitelist.error
async def whitelist_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    interaction_handler = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )

    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction_handler(
            ":x: You do not have permission to use this command.", ephemeral=True
        )
    else:
        await interaction_handler(
            f":x: An error occurred while processing the command.{error}",
            ephemeral=True,
        )


@bot.tree.command(
    name="delist", description="Remove a user from bot's approve list [admin only]"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def delist(interaction: discord.Interaction, user: discord.User):
    success = remove_whitelisted_user(str(user.id))

    if success:
        await interaction.response.send_message(
            f":white_check_mark: Successfully removed **{user.name}** from the approved whitelist.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            f":warning: **{user.name}** is not on the whitelist.", ephemeral=True
        )


@delist.error
async def delist_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    interaction_handler = (
        interaction.followup.send
        if interaction.response.is_done()
        else interaction.response.send_message
    )

    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction_handler(
            ":x: You do not have permission to use this command.", ephemeral=True
        )
    else:
        await interaction_handler(
            f":x: An error occurred while processing the command.{error}",
            ephemeral=True,
        )


@bot.tree.command(name="purge", description="Clean up messages from DMs or Servers")
@app_commands.describe(
    amount="Number of messages to delete",
    delete_others="TRUE for all messages.FALSE only purges the bot's own messages",
)
async def clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 10],
    delete_others: bool = False,
):
    if interaction.guild is None:
        await interaction.response.send_message(
            ":broom: Cleaning up my messages in our DM...", ephemeral=True
        )
        counter = 0

        async for message in interaction.channel.history(limit=100):
            if counter >= amount:
                break

            if message.author == bot.user:
                await message.delete()
                counter += 1

        await interaction.followup.send(
            f":white_check_mark: Done! Deleted {counter} of my messages.",
            ephemeral=True,
        )
        return

    if not is_user_approved(str(interaction.user.id)):
        await interaction.response.send_message(
            ":x: You do not have permission to use this command.", ephemeral=True
        )
        return

    if delete_others and not interaction.app_permissions.manage_messages:
        await interaction.followup.send(
            ":x: I need the **Manage Messages** permission to delete other users' messages.",
            ephemeral=True,
        )
        return

    def check_message(msg):  # filter
        if delete_others:
            return True
        return msg.author == bot.user

    try:
        deleted = await interaction.channel.purge(limit=amount, check=check_message)
        await interaction.followup.send(
            f":white_check_mark: Successfully purged {len(deleted)} messages.",
            ephemeral=True,
        )

    except discord.HTTPException as e:
        if (
            "Messages older than 14 days cannot be bulk deleted" in str(e)
            or e.code == 50034
        ):
            await interaction.followup.send(
                ":warning: Bulk delete failed. Falling back to manual cleanup...",
                ephemeral=True,
            )

            counter = 0
            async for message in interaction.channel.history(limit=100):
                if counter >= amount:
                    break

                if check_message(message):
                    await message.delete()
                    counter += 1

            await interaction.followup.send(
                f":white_check_mark: Fallback complete. Iteratively deleted {counter} messages.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f":warning: An unexpected error occurred: {e}", ephemeral=True
            )

    except discord.Forbidden:
        await interaction.followup.send(
            ":x: I don't have permission to delete messages in this channel.",
            ephemeral=True,
        )


@bot.tree.command(name="ask", description="Ask questions to the AI underlords")
@app_commands.describe(text="Type your question here")
async def ask(interaction: discord.Interaction, text: app_commands.Range[str, 1, 500]):
    await interaction.response.defer(thinking=True)
    # check_limits(interaction.user.id)
    try:
        response = await asyncio.to_thread(generative_response, str(text))
        await interaction.edit_original_response(content=response)
    except Exception as e:
        await interaction.edit_original_response(f"Oops! An error was caught : {e}")


@bot.tree.command(name="wordy", description="Start a game of Wordle")
async def wordle(interaction: discord.Interaction):
    if bot.wordle_active:
        await interaction.response.send_message(
            ":x: A Wordle game is already ongoing! Please wait for it to finish or end it.",
            ephemeral=True,
        )
        return

    target_word = pick_random_word()

    bot.wordle_active = True
    bot.wordle_word = target_word
    bot.wordle_guesses = []
    bot.wordle_author = interaction.user.id

    initial_embed = create_wordle_embed([], target_word)
    view = WordleEndButton(bot, interaction.user.id)

    await interaction.response.send_message(embed=initial_embed, view=view)
    bot.wordle_message = await interaction.original_response()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return

    if bot.wordle_active and message.author.id == bot.wordle_author:
        content = message.content.strip()

        if content.isalpha() and not content.startswith("!"):
            if len(content) != 5:
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                await message.channel.send(
                    f"{message.author.mention} :warning: Game is ongoing. This word does not qualify as a guess (must be exactly 5 letters).",
                    delete_after=5,
                )
                await bot.process_commands(message)
                return

            guess = content.lower()
            try:
                await message.delete()
            except discord.Forbidden:
                pass

            bot.wordle_guesses.append(guess)

            is_winner = guess == bot.wordle_word
            is_game_over = is_winner or (len(bot.wordle_guesses) >= 6)

            updated_embed = create_wordle_embed(
                bot.wordle_guesses, bot.wordle_word, game_over=is_game_over
            )

            view = discord.ui.View()
            if is_winner:
                updated_embed.color = discord.Color.green()
                updated_embed.set_footer(
                    text=f"🎉 Won by {message.author.display_name}! The word was {bot.wordle_word.upper()}."
                )

            elif len(bot.wordle_guesses) >= 6:
                updated_embed.color = discord.Color.red()
                updated_embed.set_footer(
                    text=f"💀 Game Over! The word was {bot.wordle_word.upper()}."
                )

            else:
                view = WordleEndButton(bot, bot.wordle_author)

            await bot.wordle_message.edit(
                embed=updated_embed, view=view if not is_game_over else None
            )

            if is_game_over:
                bot.wordle_active = False
                bot.wordle_guesses = []
                bot.wordle_word = ""
                bot.wordle_author = None
                bot.wordle_message = None

    await bot.process_commands(message)


keep_alive()
bot.run((os.getenv("DISCORD_SECRET")))
