from __future__ import annotations
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.__version__ import *
from src.config import EMOJIS, IGNORE_DOMAINS
from src.gemini import *
from src.media_utils import bg_extractor, download_and_compress, bg_extractor_insta_post
from src.utils import create_media_embed, CancelButtonUi, SimpleLinkUi
import tldextract
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

    @app_commands.command(name="info", description="Get some info and stats")
    async def info(self, interaction: discord.Interaction):
        latency_ms = round(self.bot.latency * 1000, 2)
        await interaction.response.send_message(f"""
        Latency : {latency_ms} ms [Latency between a HEARTBEAT and a HEARTBEAT_ACK]
        Version : {VERSION_INFO}
        Max_upload : {interaction.filesize_limit / (1024*1024)}MB ({interaction.filesize_limit}B)
        Server_members : {interaction.guild.member_count}
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

    @app_commands.command(name="insta_post", description="Share posts from Instagram")
    @app_commands.describe(link="Post link to share")
    async def insta_post(self, interaction: discord.Interaction, link: str):
        await interaction.response.send_message(content=f":white_check_mark: Queued!")

        asyncio.create_task(bg_extractor_insta_post(interaction, link))

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
                return
            if len(links) != 1:
                return

            url = links[0]

            urldata = tldextract.extract(url)
            if urldata.domain in IGNORE_DOMAINS:
                return

            message_content = message_content.replace(url, "")

            author = message.author
            stop_event = asyncio.Event()
            cancel_view = CancelButtonUi(author.id, stop_event, url)

            content = f"{EMOJIS["loading"]} Attempting to download this..."

            updated_embed = create_media_embed(author, content, None)
            ack = await message.reply(
                mention_author=True, silent=True, embed=updated_embed, view=cancel_view
            )

            async def notify_compression():
                content_compression = f"{EMOJIS["catJam"]} File too big, compressing... {EMOJIS["loading"]}"
                updated_embed = create_media_embed(author, content_compression, None)
                await ack.edit(embed=updated_embed, view=cancel_view)

            raw_file, final_file = None, None

            try:
                final_file, raw_file = await download_and_compress(
                    url=url,
                    uid=author.id,
                    req_id=message.id,
                    stop_event=stop_event,
                    on_compress_start=notify_compression,
                    timeout=180,
                )

                updated_embed = create_media_embed(author, None, message_content)
                await ack.edit(
                    attachments=[discord.File(final_file)],
                    embed=updated_embed,
                    view=SimpleLinkUi(url),
                )

                await message.delete()

            except asyncio.CancelledError:
                logger.warning(
                    f"Task aborted! By @{author.display_name} in {message.guild.name} #{message.channel.name}"
                )
                await ack.edit(
                    embed=create_media_embed(author, ":warning: Aborted by user", None),
                    view=SimpleLinkUi(url),
                    delete_after=15,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Compressor timed out! {url} by @{author.display_name} in {message.guild.name} #{message.channel.name}"
                )
                await ack.edit(
                    embed=create_media_embed(author, ":x: Operation timed out", None),
                    view=SimpleLinkUi(url),
                    delete_after=15,
                )
            except RuntimeError:
                await ack.delete()
            except discord.Forbidden:
                await ack.edit(content=f"Missing permissions to delete message.")
            except discord.NotFound:
                await ack.edit(content=f"Original URL message not found!")
            except Exception as e:
                logger.exception(f"Failed to send the file.")
                await ack.edit(
                    content=f":x: Something went wrong :( {str(e)[:75]}",
                    delete_after=15,
                )
            finally:
                for path in {raw_file, final_file}:
                    if path and os.path.exists(path):
                        try:
                            os.remove(path)
                        except FileNotFoundError:
                            pass

        return


async def setup(bot: CustomBot):
    await bot.add_cog(Utility(bot))
