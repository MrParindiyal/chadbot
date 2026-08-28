from __future__ import annotations
import asyncio
import discord
import logging
from src.config import *
import time
from typing import TYPE_CHECKING
from src.utils import is_user_approved

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.wordy.game import WordyGame


class WordyEndButton(discord.ui.View):
    def __init__(self, game_instance: WordyGame):
        super().__init__(timeout=None)
        self.game = game_instance
        self.bot = self.game.bot
        self.player = self.game.player

    @discord.ui.button(
        label="End Game", style=discord.ButtonStyle.danger, custom_id="end_wordy_game"
    )
    async def end_game_callback(
        self, interaction: discord.Interaction, _button: discord.ui.Button
    ):
        if interaction.user.id != self.player.id and not is_user_approved(
            str(interaction.user.id)
        ):
            await interaction.response.send_message(
                f"You are not the player for this game!",
                ephemeral=True,
                delete_after=15,
            )
            return

        await end_game_helper(self.game, interaction, timed_out=False, is_winner=False)


async def background_timer_task(game_instance: WordyGame, time_to_sleep: int):
    try:
        await asyncio.sleep(time_to_sleep)
        await end_game_helper(
            game_instance, interaction=None, timed_out=True, is_winner=False
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Error in background_timer_task : {e}", exc_info=e)
        await game_instance.flush_game_data()


def get_row_by_letter(keyboard: dict, alphabet: str) -> str:
    return keyboard["track"][alphabet]


def return_formatted_row(row_num: int, keyboard: dict) -> str:
    row = f"row{row_num}"
    out = ""

    for char in keyboard[row]:
        out += f"{EMOJIS[f"{keyboard[row][char]}"]} "
    return out


def set_explored_color(keyboard: dict, letter: str, color: str):
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
    guesses: list[str],
    target_word: str,
    difficulty: str,
    explored: dict[str, dict[str, str]],
    player: discord.User | discord.Member | None,
    end_time: int | None = None,
    time_left: float | int | None = None,
    game_over: bool = False,
):
    if game_over and time_left is not None:
        mins, secs = divmod(max(0, int(time_left)), 60)
        time_display = f"`{mins:02d}:{secs:02d}`"

    elif end_time is not None:
        time_display = f"<t:{end_time}:R>"

    else:
        time_display = "`00:00`"

    embed = discord.Embed(
        title=":green_square: Discord Wordy :yellow_square:",
        description=f"""Guess the 5-letter word! Type your guesses in chat.
        Difficulty : `{difficulty}`
        **Time Remaining:** {time_display}\n\n""",
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

    return embed


async def end_game_helper(
    game: WordyGame,
    interaction: discord.Interaction | None,
    timed_out: bool,
    is_winner: bool,
):
    if not game.wordy_active and interaction != None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "There is no active wordy game running right now.", ephemeral=True
            )
        return

    player = game.player
    time_left = max(0, game.unix_end_timer - time.time()) if not timed_out else 0

    embed = create_wordy_embed(
        game.wordy_guesses,
        game.wordy_word,
        game.difficulty,
        game.explored,
        game.wordy_author,
        game.unix_end_timer,
        time_left,
        game_over=True,
    )

    if is_winner:
        embed.color = discord.Color.green()
        embed.set_footer(
            text=f"🎉 Won by {player.display_name}! The word was {game.wordy_word.upper()}."
        )

    elif timed_out:
        embed.color = discord.Color.darker_grey()
        embed.set_footer(text=f"⏰ Time's up! The word was {game.wordy_word.upper()}.")

    else:
        embed.color = discord.Color.red()
        embed.set_footer(text=f"💀 Game Over! The word was {game.wordy_word.upper()}.")

    current_task = asyncio.current_task()
    if (
        game.wordy_timer_task
        and not game.wordy_timer_task.done()
        and game.wordy_timer_task != current_task
    ):
        game.wordy_timer_task.cancel()
    game.wordy_timer_task = None

    try:
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=None)
        elif game.wordy_message:
            await game.wordy_message.edit(embed=embed, view=None)
    except discord.HTTPException:
        pass

    await game.flush_game_data()
