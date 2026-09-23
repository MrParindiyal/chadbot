from __future__ import annotations
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.__version__ import *
from src.config import EMOJIS
from src.gemini import *
from src.media_utils import bg_extractor, download_ig_media, compressor
from typing import TYPE_CHECKING
from urlextract import URLExtract

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from main import CustomBot


class Utility(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot

    @app_commands.command(name="ping", description="Returns the bot's gateway latency")
    async def ping(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000, 2)
        await interaction.response.send_message(f"pong! ({latency_ms} ms)")

    @app_commands.command(
        name="version", description="Bot's version and What's New? info"
    )
    async def version(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"""
            This instance of bot is running `v{VERSION_INFO}` !\n{WHATS_NEW}
            """)

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

    @app_commands.command(name="insta", description="Share reels from Instagram")
    @app_commands.describe(link="Reel link to share")
    async def insta(self, interaction: discord.Interaction, link: str):
        await interaction.response.send_message(content=f":white_check_mark: Queued!")

        asyncio.create_task(bg_extractor(interaction, link))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.content and not message.author.bot and not message.attachments:
            message_content = message.content.strip()
            extractor = URLExtract(
                extract_email=False, cache_dns=False, extract_localhost=False
            )
            try:
                links = extractor.find_urls(message_content, only_unique=True)
            except:
                logger.warning(f"URLextractor failed...")

            if len(links) != 1:
                return
            message_content = message_content.replace(links[0], "")
            ack = await message.reply(
                content=f"{EMOJIS["loading"]} Attempting to download this...",
                mention_author=True,
                silent=True,
            )

            result = await asyncio.to_thread(
                download_ig_media, links[0], message.author.id, message.id
            )
            if not result["success"]:
                try:
                    await ack.delete()
                except:
                    pass
                return

            file_path = result["file_path"]
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            if file_size < 20:
                final_file = file_path
            else:
                await ack.edit(
                    content=f"{EMOJIS["catJam"]} File too big, compressing... {EMOJIS["loading"]}"
                )
                file_name = "_".join(
                    str(os.path.basename(file_path))
                    .removesuffix(".mp4")
                    .split("_")[1:-1]
                )
                final_file = await asyncio.to_thread(
                    compressor,
                    file_path,
                    output_file=f"./data/downloads/compressed/{message.author.id}_{file_name}.compressed_{message.id}.mp4",
                )

            try:
                await ack.edit(
                    content=f"{message_content}\n\n\n> _Originally sent by_:<@{message.author.id}>\n> _Source_:||{links[0]}||",
                    attachments=[discord.File(final_file)],
                )
                await message.delete()
            except discord.Forbidden:
                await ack.edit(
                    content=f"Missing permissions to delete message.", delete_after=15
                )
            except discord.NotFound:
                await ack.edit(
                    content=f"Original URL message not found!", delete_after=15
                )
            except Exception as e:
                logger.exception(
                    f"Failed to send the file. RawSize:{file_size:.2f}MB | CompressedSize:{(os.path.getsize(final_file) / (1024 * 1024)):.2f}MB"
                )
                await ack.edit(
                    content=f":x: Something went wrong :( {str(e)[:75]}",
                    delete_after=15,
                )
            finally:
                for path in {file_path, final_file}:
                    try:
                        os.remove(path)
                    except FileNotFoundError:
                        pass

        return


async def setup(bot: CustomBot):
    await bot.add_cog(Utility(bot))
