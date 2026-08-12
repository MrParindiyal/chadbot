import discord
import random
from src.config import *

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


class WordyEndButton(discord.ui.View):
    def __init__(self, bot_instance, player_id):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.interacting_author = player_id

    @discord.ui.button(
        label="End Game", style=discord.ButtonStyle.danger, custom_id="end_wordy_game"
    )
    async def end_game_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not self.bot.wordy_active:
            await interaction.response.send_message(
                "There is no active wordy game running right now.", ephemeral=True
            )
            return

        if interaction.user.id == self.interacting_author:
            embed = create_wordy_embed(
                self.bot.wordy_guesses,
                self.bot.wordy_word,
                self.bot.explored,
                interaction.user,
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

        # Reset bot state
        self.bot.wordy_active = False
        self.bot.wordy_word = ""
        self.bot.wordy_guesses = []
        self.bot.wordy_message = None
        self.bot.wordy_author = None


def get_row_by_letter(keyboard, alphabet):
    return keyboard["track"][alphabet]


def return_formatted_row(row_num: int, keyboard: dict) -> str:
    row = f"row{row_num}"
    out = ""

    for char in keyboard[row]:
        out += f"{EMOJIS[f"{keyboard[row][char]}"]} "
    return out


def create_wordy_embed(guesses, target_word, explored, player, game_over=False):
    embed = discord.Embed(
        title=":green_square: Discord Wordy :yellow_square:",
        description="Guess the 5-letter word! Type your guesses in chat.\n\n\n",
        color=discord.Color.blurple(),
    )
    embed.set_thumbnail(url=player.display_avatar.url)
    board_text = ""
    for guess in guesses:
        row_str = ""
        for i, letter in enumerate(guess):
            letter_capital = letter.upper()
            row = get_row_by_letter(explored, letter_capital)
            if letter == target_word[i]:
                row_str += f"{EMOJIS[f"green_{letter_capital}"]} "
                explored[row][letter_capital] = f"green_{letter_capital}"
            elif letter in target_word:
                row_str += f"{EMOJIS[f"yellow_{letter.upper()}"]} "
                if explored[row][letter_capital][:5] != "green":
                    explored[row][letter_capital] = f"yellow_{letter_capital}"
            else:
                row_str += f"{EMOJIS[f"grey_{letter_capital}"]} "
                explored[row][letter_capital] = f"grey_{letter_capital}"

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
