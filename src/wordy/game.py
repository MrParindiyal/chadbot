from __future__ import annotations
from typing import TYPE_CHECKING
import copy
import discord
from src.config import *
import time
import asyncio
import random
import logging

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from main import CustomBot


def pick_random_word() -> str:
    return random.choice(WORDS)


class WordyGame:
    def __init__(
        self, bot: CustomBot, interaction: discord.Interaction, difficulty: str
    ):
        self.bot: CustomBot = bot

        self.interaction: discord.Interaction = interaction
        self.channelid: int | None = interaction.channel_id
        self.guildid: int | None = interaction.guild_id
        self.player: discord.User | discord.Member = interaction.user
        self.embed: discord.Embed | None = None
        self.image: bool = False
        self.threadid: int | None = None
        self.wordy_active: bool = True
        self.wordy_word: str = pick_random_word()
        self.wordy_guesses: list[str] = []
        self.wordy_message: discord.InteractionMessage | None = None
        self.wordy_author = self.player
        self.explored: dict[str, dict[str, str]] = copy.deepcopy(KEYBOARD)
        self.unix_end_timer: int = int(time.time() + WORDY_TIMER[difficulty])
        self.wordy_timer_task: asyncio.Task[None] | None = None
        self.difficulty: str = difficulty

    async def flush_game_data(self) -> None:
        bot = self.bot
        guild = bot.get_guild(self.guildid)
        thread = guild.get_channel_or_thread(
            self.threadid
        )  # TODO: replace with fetch_channel if None is found
        await thread.delete()
        self.threadid = None
        del bot.wordy_games[self.player.id]
