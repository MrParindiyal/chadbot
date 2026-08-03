import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

load_dotenv()

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    app_emojis = await bot.fetch_application_emojis()
    if app_emojis != []:
        with open("app_emojis.csv", "w", encoding="utf-8") as file:
            file.write("emoji_name, emoji_id\n")
            for emoji in app_emojis:
                file.write(f'"{emoji.name}", "{emoji}"\n')
        print("Successfully parsed app emojis!")
    else:
        print("No App Emojis found!")
bot.run(os.getenv("DISCORD_SECRET"))
