from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
from google.genai.errors import APIError, ClientError
import logging
from logging.handlers import RotatingFileHandler
import os
from ratelimit import RateLimitException
from webserver import keep_alive

load_dotenv()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s : %(message)s")
file_handler = RotatingFileHandler(
    filename="bot.log", maxBytes=8 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(formatter)
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(console_handler)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
logger.info("Startin up...")


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
        self.tree.error(self.on_app_command_error)

        self.wordy_active = False
        self.wordy_word = ""
        self.wordy_guesses = []
        self.wordy_message = None
        self.wordy_author = None
        self.explored = None
        self.unix_end_timer = -1
        self.wordy_timer_task = None

    async def on_ready(self):
        logger.info(f"Logged in successfully as {self.user} (ID: {self.user.id})")

    async def setup_hook(self):
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("__"):
                await self.load_extension(f"cogs.{filename[:-3]}")
        logger.info("Syncing slash commands...")
        synced = await self.tree.sync()
        logger.info(f"Synced {len(synced)} command(s).")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        """ "Base error handler"""
        original_err = getattr(error, "original", error)
        command_name = (
            f"/{interaction.command.name}" if interaction.command else "Unknown Command"
        )

        if isinstance(original_err, RateLimitException):
            msg = f"Oops! You are being rate-limited. Retry after **{round(original_err.period_remaining, 1)}** seconds."
            logger.warning(
                f"Rate limit hit by {interaction.user} in command /{interaction.command.name}"
            )
        elif isinstance(original_err, (APIError, ClientError)):
            msg = f"Oops! An API error was caught : {original_err.code} {original_err.status}"
            logger.error(
                f"API Error in /{interaction.command.name}: {original_err}",
                exc_info=original_err,
            )
        else:
            msg = f"Oops! An unexpected error occurred: {original_err}"
            logger.error(
                f"Unhandled error in /{interaction.command.name}: {original_err}",
                exc_info=original_err,
            )

        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(content=msg)
            else:
                await interaction.response.send_message(content=msg, ephemeral=True)
        except discord.HTTPException as e:
            logger.warning(
                f"Could not send error response to user for {command_name}: {e}"
            )


bot = CustomBot()


keep_alive()
bot.run((os.getenv("DISCORD_SECRET")))
