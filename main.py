from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ext import commands

import os
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
            command_prefix='!',
            case_insensitive=True,
            intents=intents,
            activity=game_activity,
            status=discord.Status.online
        )

    async def setup_hook(self):
        await self.tree.sync()


bot = CustomBot()

@bot.event
async def on_ready():
    print(f"We have logged in successfully as {bot.user}")


@bot.tree.command(
    name="ping", description="Returns the bot's gateway latency")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000, 2)
    await interaction.response.send_message(f"pong! ({latency_ms} ms)")

keep_alive()
bot.run((os.getenv("DISCORD_SECRET")))
