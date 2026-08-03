import discord
import random

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


class WordleEndButton(discord.ui.View):
    def __init__(self, bot_instance, player_id):
        super().__init__(timeout=None)
        self.bot = bot_instance
        self.interacting_author = player_id

    @discord.ui.button(label="End Game", style=discord.ButtonStyle.danger, custom_id="end_wordle_game")
    async def end_game_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.bot.wordle_active:
            await interaction.response.send_message("There is no active Wordle game running right now.", ephemeral=True)
            return

        if interaction.user.id == self.interacting_author:
            embed = create_wordle_embed(self.bot.wordle_guesses, self.bot.wordle_word, game_over=True)
            embed.color = discord.Color.red()
        else:
            await interaction.response.send_message("You are not the player for this game!", ephemeral=True, delete_after=50)
            return

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        
        # Reset bot state
        self.bot.wordle_active = False
        self.bot.wordle_word = ""
        self.bot.wordle_guesses = []
        self.bot.wordle_message = None
        self.bot.wordle_author = None


def create_wordle_embed(guesses, target_word, game_over=False):
    embed = discord.Embed(
        title=":green_square: Discord Wordle :yellow_square:",
        description="Guess the 5-letter word! Type your guesses in chat.",
        color=discord.Color.blurple()
    )

    board_text = ""
    for guess in guesses:
        row_str = ""
        for i, letter in enumerate(guess):
            if letter == target_word[i]:
                row_str += ":green_square: "
            elif letter in target_word:
                row_str += ":yellow_square: "
            else:
                row_str += ":black_large_square: "
        board_text += f"{row_str} (`{guess.upper()}`)\n"

    remaining_rows = 6 - len(guesses)
    for _ in range(remaining_rows):
        board_text += ":black_large_square: :black_large_square: :black_large_square: :black_large_square: :black_large_square:\n"
        
    embed.add_field(name="Game Board", value=board_text, inline=False)

    if game_over:
        embed.set_footer(text=f"Game Ended. The word was: {target_word.upper()}")
    else:
        embed.set_footer(text=f"Guesses used: {len(guesses)}/6 | Type a 5-letter word to play!")
        
    return embed

def pick_random_word():
    return "words"
    # return random.choice(words)