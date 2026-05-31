from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ext import commands
from src.helpers import *
import os
from src.response import random_response, hook
from webserver import keep_alive

load_dotenv()

class CustomBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.messages = True
        game_activity = discord.Game(name="with your Mom 😇")

        super().__init__(
            command_prefix='!',
            case_insensitive=True,
            intents=intents,
            activity=game_activity,
            status=discord.Status.online
        )

    async def setup_hook(self):
        await self.tree.sync()


bot = CustomBot()

@bot.event
async def on_ready():
    print(f"We have logged in successfully as {bot.user}")


@bot.tree.command(
    name="ping", description="Returns the bot's gateway latency")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000, 2)
    await interaction.response.send_message(f"pong! ({latency_ms} ms)")

@bot.tree.command(name="whitelist", description="Add a user to bot's approve list [admin only]")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def whitelist(interaction: discord.Interaction, user: discord.User):
    await interaction.response.defer(ephemeral=True)
    success = whitelist_user(user.name)

    if success:
        await interaction.followup.send(f":white_check_mark: Successfully added **{user.name}** to the approved whitelist.", ephemeral=True)
    else:
        await interaction.followup.send(f":warning: **{user.name}** is already on the whitelist.", ephemeral=True)

@whitelist.error
async def whitelist_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    interaction_handler = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message

    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction_handler(":x: You do not have permission to use this command.", ephemeral=True)
    else:
        await interaction_handler(f":x: An error occurred while processing the command.{error}", ephemeral=True)


@bot.tree.command(name="delist", description="Remove a user from bot's approve list [admin only]")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.guild_only()
async def delist(interaction: discord.Interaction, user: discord.User):
    success = remove_whitelisted_user(user.name)

    if success:
        await interaction.response.send_message(f":white_check_mark: Successfully removed **{user.name}** from the approved whitelist.", ephemeral=True)
    else:
        await interaction.response.send_message(f":warning: **{user.name}** is not on the whitelist.", ephemeral=True)

@delist.error
async def delist_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    interaction_handler = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message

    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction_handler(":x: You do not have permission to use this command.", ephemeral=True)
    else:
        await interaction_handler(f":x: An error occurred while processing the command.{error}", ephemeral=True)

@bot.tree.command(name="purge", description="Clean up messages from DMs or Servers")
@app_commands.describe(
    amount="Number of messages to delete",
    delete_others="TRUE for all messages.FALSE only purges the bot's own messages"
)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int,1,10], delete_others: bool = False):
    if interaction.guild is None:
        await interaction.response.send_message("🧹 Cleaning up my messages in our DM...", ephemeral=True)
        counter = 0

        async for message in interaction.channel.history(limit=100):
            if counter >= amount:
                break
            
            if message.author == bot.user:
                await message.delete()
                counter += 1
        
        await interaction.followup.send(f":white_check_mark: Done! Deleted {counter} of my messages.", ephemeral=True)
        return


    if not is_user_approved(interaction.user.name):
        await interaction.response.send_message(":x: You do not have permission to use this command.", ephemeral=True)
        return

    if delete_others and not interaction.app_permissions.manage_messages:
        await interaction.followup.send(":x: I need the **Manage Messages** permission to delete other users' messages.", ephemeral=True)
        return
    
    def check_message(msg): # filter
        if delete_others:
            return True
        return msg.author == bot.user

    try:
        deleted = await interaction.channel.purge(limit=amount, check=check_message)
        await interaction.followup.send(f":white_check_mark: Successfully purged {len(deleted)} messages.", ephemeral=True)

    except discord.HTTPException as e:
        if "Messages older than 14 days cannot be bulk deleted" in str(e) or e.code == 50034:
            await interaction.followup.send(":warning: Bulk delete failed. Falling back to manual cleanup...", ephemeral=True)
            
            counter = 0
            async for message in interaction.channel.history(limit=100):
                if counter >= amount:
                    break
                
                if check_message(message):
                    await message.delete()
                    counter += 1
            
            await interaction.followup.send(f":white_check_mark: Fallback complete. Iteratively deleted {counter} messages.", ephemeral=True)
        else:
            await interaction.followup.send(f":warning: An unexpected error occurred: {e}", ephemeral=True)
            
    except discord.Forbidden:
        await interaction.followup.send(":x: I don't have permission to delete messages in this channel.", ephemeral=True)

keep_alive()
bot.run((os.getenv("DISCORD_SECRET")))
