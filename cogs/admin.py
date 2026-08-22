from __future__ import annotations
import discord
from discord import app_commands
from discord.ext import commands
import logging
from src.helpers import *
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from main import CustomBot


class Admin(commands.Cog):
    def __init__(self, bot: CustomBot):
        self.bot = bot

    @app_commands.command(
        name="whitelist", description="Add a user to bot's approve list [admin only]"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def whitelist(self, interaction: discord.Interaction, user: discord.User):
        await interaction.response.defer(ephemeral=True)
        success = whitelist_user(str(user.id))

        if success:
            await interaction.followup.send(
                f":white_check_mark: Successfully added **{user.name}** to the approved whitelist.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f":warning: **{user.name}** is already on the whitelist.",
                ephemeral=True,
            )

    @app_commands.command(
        name="delist", description="Remove a user from bot's approve list [admin only]"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def delist(self, interaction: discord.Interaction, user: discord.User):
        success = remove_whitelisted_user(str(user.id))

        if success:
            await interaction.response.send_message(
                f":white_check_mark: Successfully removed **{user.name}** from the approved whitelist.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f":warning: **{user.name}** is not on the whitelist.", ephemeral=True
            )

    @app_commands.command(
        name="purge", description="Clean up messages from DMs or Servers"
    )
    @app_commands.describe(
        amount="Number of messages to delete",
        delete_others="TRUE for all messages.FALSE only purges the bot's own messages",
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 10],
        delete_others: bool = False,
    ):
        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            counter = 0

            async for message in interaction.channel.history(limit=100):
                if counter >= amount:
                    break

                if message.author == self.bot.user:
                    await message.delete()
                    counter += 1

            await interaction.followup.send(
                f":white_check_mark: Done! Deleted {counter} of my messages.",
                ephemeral=True,
            )
            return

        if not is_user_approved(str(interaction.user.id)):
            await interaction.followup.send(
                ":x: You do not have permission to use this command.", ephemeral=True
            )
            return

        if delete_others and not interaction.app_permissions.manage_messages:
            await interaction.followup.send(
                ":x: I need the **Manage Messages** permission to delete other users' messages.",
                ephemeral=True,
            )
            return

        def check_message(msg):  # filter
            if delete_others:
                return True
            return msg.author == self.bot.user

        try:
            deleted = await interaction.channel.purge(limit=amount, check=check_message)
            logger.info(
                f"Purged {len(deleted)} messages in #{interaction.channel} (User: {interaction.user})"
            )
            await interaction.followup.send(
                f":white_check_mark: Successfully purged {len(deleted)} messages.",
                ephemeral=True,
            )

        except discord.HTTPException as e:
            if (
                "Messages older than 14 days cannot be bulk deleted" in str(e)
                or e.code == 50034
            ):
                logger.warning(
                    f"Bulk delete restriction hit in #{interaction.channel}. Switching to manual deletion fallback."
                )
                await interaction.followup.send(
                    ":warning: Bulk delete failed. Falling back to manual cleanup...",
                    ephemeral=True,
                )

                counter = 0
                async for message in interaction.channel.history(limit=100):
                    if counter >= amount:
                        break

                    if check_message(message):
                        await message.delete()
                        counter += 1

                logger.info(
                    f"Manual fallback complete in #{interaction.channel}. Deleted {counter} messages."
                )
                await interaction.followup.send(
                    f":white_check_mark: Fallback complete. Iteratively deleted {counter} messages.",
                    ephemeral=True,
                )
            else:
                logger.error(
                    f"Unexpected HTTP error during purge in #{interaction.channel}: {e}",
                    exc_info=e,
                )
                await interaction.followup.send(
                    f":warning: An unexpected error occurred: {e}", ephemeral=True
                )

        except discord.Forbidden:
            logger.warning(
                f"Permission denied while attempting to purge #{interaction.channel} (Requested by {interaction.user})"
            )
            await interaction.followup.send(
                ":x: I don't have permission to delete messages in this channel.",
                ephemeral=True,
            )


async def setup(bot: CustomBot):
    await bot.add_cog(Admin(bot))
