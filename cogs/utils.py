import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.gemini import *

logger = logging.getLogger(__name__)


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Returns the bot's gateway latency")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000, 2)
        await interaction.response.send_message(f"pong! ({latency_ms} ms)")

    @app_commands.command(name="ask", description="Ask questions to the AI underlords")
    @app_commands.describe(text="Type your question here")
    async def ask(self, interaction: discord.Interaction, text: str):
        if len(text) > 500:
            await interaction.response.send_message(
                "Your question must be under 500 characters.",
                ephemeral=True,
                delete_after=10,
            )
            return
        logger.info(
            f"User: {interaction.user} ID: {interaction.user.id} issued /ask with query: '{text}'"
        )
        await interaction.response.defer(thinking=True)
        response = await asyncio.to_thread(generative_response, str(text))
        await interaction.edit_original_response(content=response)

    @app_commands.command(
        name="search", description="Smart search with up-to-date info, LLM powered"
    )
    @app_commands.describe(text="Type your query here")
    async def search(self, interaction: discord.Interaction, text: str):
        if len(text) > 500:
            await interaction.response.send_message(
                "Your question must be under 500 characters.",
                ephemeral=True,
                delete_after=10,
            )
            return

        logger.info(
            f"User: {interaction.user} ID: {interaction.user.id} issued /search with query: '{text}'"
        )
        await interaction.response.defer(thinking=True)
        response = await asyncio.to_thread(generative_search, str(text))
        await interaction.edit_original_response(content=response)


async def setup(bot):
    await bot.add_cog(Utility(bot))
