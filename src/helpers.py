import asyncio
import discord
from discord.ext import commands
import logging
import random
from src.config import *
import time

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


def pick_random_word():
    return random.choice(WORDS)


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


def flush_game_data(bot: commands.Bot):
    bot.wordy_active = False
    bot.wordy_word = ""
    bot.wordy_guesses = []
    bot.wordy_message = None
    bot.wordy_author = None
    bot.explored = None
    bot.unix_end_timer = -1
    bot.wordy_timer_task = None


async def background_timer_task(bot_instance, time_to_sleep):
    try:
        await asyncio.sleep(time_to_sleep)
        await end_game_helper(
            bot_instance, interaction=None, timed_out=True, is_winner=False
        )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"Error in background_timer_task : {e}", exc_info=e)
        flush_game_data(bot_instance)


def create_wordy_embed(
    guesses,
    target_word,
    explored,
    player,
    end_time=None,
    time_left=None,
    game_over=False,
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
        description=f"""Guess the 5-letter word! Type your guesses in chat.\n
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
    bot: commands.Bot, interaction: discord.Interaction, timed_out, is_winner
):
    if not bot.wordy_active and interaction != None:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "There is no active wordy game running right now.", ephemeral=True
            )
        return

    player = bot.wordy_author
    time_left = max(0, bot.unix_end_timer - time.time()) if not timed_out else 0

    embed = create_wordy_embed(
        bot.wordy_guesses,
        bot.wordy_word,
        bot.explored,
        bot.wordy_author,
        bot.unix_end_timer,
        time_left,
        game_over=True,
    )

    if is_winner:
        embed.color = discord.Color.green()
        embed.set_footer(
            text=f"🎉 Won by {player.display_name}! The word was {bot.wordy_word.upper()}."
        )

    elif timed_out:
        embed.color = discord.Color.darker_grey()
        embed.set_footer(text=f"⏰ Time's up! The word was {bot.wordy_word.upper()}.")

    else:
        embed.color = discord.Color.red()
        embed.set_footer(text=f"💀 Game Over! The word was {bot.wordy_word.upper()}.")

    current_task = asyncio.current_task()
    if (
        bot.wordy_timer_task
        and not bot.wordy_timer_task.done()
        and bot.wordy_timer_task != current_task
    ):
        bot.wordy_timer_task.cancel()
    bot.wordy_timer_task = None

    try:
        if interaction and not interaction.response.is_done():
            await interaction.response.edit_message(embed=embed, view=None)
        elif bot.wordy_message:
            await bot.wordy_message.edit(embed=embed, view=None)
    except discord.HTTPException:
        pass

    flush_game_data(bot)


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
        if interaction.user.id != self.player.id and not is_user_approved(
            str(interaction.user.id)
        ):
            await interaction.response.send_message(
                f"You are not the player for this game!",
                ephemeral=True,
                delete_after=15,
            )
            return

        await end_game_helper(self.bot, interaction, timed_out=False, is_winner=False)
