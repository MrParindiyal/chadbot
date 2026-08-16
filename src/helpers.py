import asyncio
import discord
from discord.ext import commands
import logging
import random
from src.config import *

logger = logging.getLogger(__name__)

try:
    with open("./data/approved.txt", "r") as f:
        approved_users = {line.strip() for line in f if line.strip()}
except FileNotFoundError:
    approved_users = set()


def is_user_approved(userid: str) -> bool:
    return (userid) in approved_users


def whitelist_user(userid: str) -> bool:
    if is_user_approved(userid):
        return False

    with open("./data/approved.txt", "a") as f:
        f.write(f"{userid}\n")

    approved_users.add(userid)

    return True


def remove_whitelisted_user(userid: str) -> bool:
    if not is_user_approved(userid):
        return False

    approved_users.discard((userid))

    with open("./data/approved.txt", "w") as f:
        for user in approved_users:
            f.write(f"{user}\n")

    return True


def flush_game_data(bot: commands.Bot):
    bot.wordy_active = False
    bot.wordy_word = ""
    bot.wordy_guesses = []
    bot.wordy_message = None
    bot.wordy_author = None
    bot.explored = None
    bot.unix_end_timer = -1
    bot.wordy_timer_task = None


class WordyEndButton(discord.ui.View):
    def __init__(self, bot_instance, player):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.player: discord.User = player

    @discord.ui.button(
        label="End Game", style=discord.ButtonStyle.danger, custom_id="end_wordy_game"
    )
    async def end_game_callback(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if not self.bot.wordy_active:
            await interaction.response.send_message(
                "There is no active wordy game running right now.", ephemeral=True
            )
            return

        if interaction.user.id == self.player.id or is_user_approved(
            str(interaction.user.id)
        ):
            embed = create_wordy_embed(
                self.bot.wordy_guesses,
                self.bot.wordy_word,
                self.bot.explored,
                self.player,
                self.bot.unix_end_timer,
                game_over=True,
            )
            embed.color = discord.Color.red()
        else:
            await interaction.response.send_message(
                "You are not the player for this game!", ephemeral=True, delete_after=50
            )
            return

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        if self.bot.wordy_timer_task:
            self.bot.wordy_timer_task.cancel()
            self.bot.wordy_timer_task = None
        # Reset bot state
        flush_game_data(self.bot)


def get_row_by_letter(keyboard, alphabet):
    return keyboard["track"][alphabet]


def return_formatted_row(row_num: int, keyboard: dict) -> str:
    row = f"row{row_num}"
    out = ""

    for char in keyboard[row]:
        out += f"{EMOJIS[f"{keyboard[row][char]}"]} "
    return out


def set_explored_color(keyboard, letter, color):
    letter = letter.upper()
    row = get_row_by_letter(keyboard, letter)

    if color in ("green", "yellow", "grey"):
        match color:
            case "grey":
                if keyboard[row][letter].startswith("unexplored"):
                    keyboard[row][letter] = f"{color}_{letter}"

            case "yellow":
                if not keyboard[row][letter].startswith("green"):
                    keyboard[row][letter] = f"{color}_{letter}"

            case "green":
                keyboard[row][letter] = f"{color}_{letter}"

    else:
        logger.warning(f"Wrong color was provided : {color}")


def create_wordy_embed(
    guesses, target_word, explored, player, timer=None, game_over=False
):
    embed = discord.Embed(
        title=":green_square: Discord Wordy :yellow_square:",
        description=f"""Guess the 5-letter word! Type your guesses in chat.\n
        **Time Remaining:** <t:{timer}:R>\n\n""",
        color=discord.Color.blurple(),
    )
    embed.set_thumbnail(url=player.display_avatar.url)
    board_text = ""
    for guess in guesses:
        guess = list(guess)
        target = list(target_word)
        row_str_list = [""] * len(guess)

        for i, letter in enumerate(guess):
            letter_capital = letter.upper()
            row_str_list[i] = f"{EMOJIS[f"grey_{letter_capital}"]} "
            set_explored_color(explored, letter_capital, "grey")
            if letter == target[i]:
                row_str_list[i] = f"{EMOJIS[f"green_{letter_capital}"]} "
                set_explored_color(explored, letter_capital, "green")
                guess[i] = None
                target[i] = None

        for i, letter in enumerate(guess):
            if letter is None:
                pass
            elif letter in target:
                row_str_list[i] = f"{EMOJIS[f"yellow_{letter.upper()}"]} "
                set_explored_color(explored, letter, "yellow")
                target[target.index(letter)] = None

        row_str = "".join(row_str_list)
        board_text += f"{row_str}\n"

    remaining_rows = 6 - len(guesses)
    for _ in range(remaining_rows):
        board_text += ":black_large_square: :black_large_square: :black_large_square: :black_large_square: :black_large_square:\n"

    content = ""
    for i, key in enumerate(explored):
        if key != "track":
            content += " ‎ " * i * 4
            content += return_formatted_row(i + 1, explored)
            content += "\n"
        else:
            content += "\n\n"

    embed.add_field(name="Exploration status", value=content, inline=False)
    embed.add_field(name="Game Board", value=board_text, inline=False)

    if game_over:
        embed.set_footer(text=f"Game Ended. The word was: {target_word.upper()}")
    else:
        embed.set_footer(
            text=f"Guesses used: {len(guesses)}/6 | Type a 5-letter word to play!"
        )

    return embed


def pick_random_word():
    return random.choice(WORDS)


async def background_timer_task(bot_instance, n):
    try:
        await asyncio.sleep(n)

        if bot_instance.wordy_active == True:
            expired = create_wordy_embed(
                bot_instance.wordy_guesses,
                bot_instance.wordy_word,
                bot_instance.explored,
                None,
                bot_instance.unix_end_timer,
                game_over=True,
            )
            expired.color = discord.Color.red()
            expired.set_footer(
                text=f"he game expired. The word was {bot_instance.wordy_word.upper()}."
            )
            await bot_instance.wordy_message.edit(embed=expired, view=None)
            flush_game_data(bot_instance)

    except asyncio.CancelledError:
        # Task cancelled, game finished before timeout.
        pass
