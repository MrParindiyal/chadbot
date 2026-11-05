from __future__ import annotations
from typing import TYPE_CHECKING
import asyncio
import discord
import logging
import os
import signal

logger = logging.getLogger(__name__)
APPROVED_FILE = "./data/approved.txt"
os.makedirs(os.path.dirname(APPROVED_FILE), exist_ok=True)

if TYPE_CHECKING:
    from main import CustomBot

try:
    with open(APPROVED_FILE, "r") as f:
        approved_users = {line.strip() for line in f if line.strip()}
except FileNotFoundError:
    approved_users = set()


def is_user_approved(user_id: str) -> bool:
    return user_id in approved_users


def whitelist_user(user_id: str) -> bool:
    if is_user_approved(user_id):
        return False

    with open(APPROVED_FILE, "a") as f:
        f.write(f"{user_id}\n")

    approved_users.add(user_id)

    return True


def remove_whitelisted_user(user_id: str) -> bool:
    if not is_user_approved(user_id):
        return False

    approved_users.discard(user_id)

    with open(APPROVED_FILE, "w") as f:
        for user in approved_users:
            f.write(f"{user}\n")

    return True


def create_media_embed(user: discord.User, title: str | None, caption: str | None):
    embed = discord.Embed(
        color=discord.Color.from_rgb(85, 125, 135),
        title=title,
        description=f"{f"**{caption}**" if caption is not None else ""}\n> _Original by_ : <@{user.id}>",
    )
    return embed


async def run_cmd_cancellable(
    cmd: list[str],
    stop_event: asyncio.Event | None = None,
    capture_stdout: bool = False,
    timeout: float | None = None,
    kill_proc_group: bool = False,
) -> bytes:
    """Runs a subprocess asynchronously and kills it cleanly on cancellation or stop_event."""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE if capture_stdout else None,
        stderr=asyncio.subprocess.PIPE if capture_stdout else None,
        start_new_session=kill_proc_group,  # Isolates child processes into a group if True
    )

    comm_task = asyncio.create_task(process.communicate())
    tasks: set[asyncio.Task] = {comm_task}

    stop_task = None

    if stop_event is not None:
        stop_task = asyncio.create_task(stop_event.wait())
        tasks.add(stop_task)

    try:
        done, pending = await asyncio.wait(
            tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()

        if not done:  # Timed out (neither task finished within `timeout` seconds)
            await _terminate_process(process, kill_proc_group=kill_proc_group)
            await asyncio.gather(*tasks, return_exceptions=True)
            raise asyncio.TimeoutError(f"Command {cmd[0]} timed out after {timeout}s")

        if stop_task and stop_task in done:  # stop_event was triggered
            raise asyncio.CancelledError(f"Command {cmd[0]} stopped via stop_event")

        # process finished
        stdout_bytes, stderr_bytes = comm_task.result()
        if process.returncode != 0:
            err_msg = (
                stderr_bytes.decode("utf-8", errors="replace").strip()
                if stderr_bytes
                else ""
            )
            raise RuntimeError(
                f">>> {cmd[0]} failed, exit code : {process.returncode}\n{err_msg}"
            )

        return stdout_bytes or b""

    except asyncio.CancelledError:
        # outer asyncio.Task.cancel() call and stop_event trigger
        for t in tasks:
            t.cancel()
        await _terminate_process(process, kill_proc_group=kill_proc_group)
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _terminate_process(
    process: asyncio.subprocess.Process,
    timeout: float = 3.0,
    kill_proc_group: bool = False,
):
    """Sends SIGTERM first, then SIGKILL if it hangs."""

    if process.returncode is not None:
        return

    try:
        if kill_proc_group and hasattr(os, "killpg"):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()

        await asyncio.wait_for(process.wait(), timeout=timeout)

    except asyncio.TimeoutError:
        if kill_proc_group and hasattr(os, "killpg"):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        else:
            process.kill()

        await process.wait()

    except ProcessLookupError:
        # Process already exited right before signal was sent
        pass


class CancelButtonUi(discord.ui.View):
    def __init__(self, owner_id: int, stop_event: asyncio.Event, url: str):
        super().__init__(timeout=180)

        self.owner_id = owner_id
        self.stop_event = stop_event
        self.url = url
        self.add_item(
            discord.ui.Button(
                label="🔗Source", style=discord.ButtonStyle.grey, url=self.url
            )
        )

    @discord.ui.button(
        label="❌ Abort",
        style=discord.ButtonStyle.grey,
        custom_id="cancel",
    )
    async def abort_download(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        is_admin = interaction.user.guild_permissions.administrator
        is_approved = is_user_approved(interaction.user.id)

        if (is_admin or is_approved) or interaction.user.id == self.owner_id:
            # requesting party is verified
            self.stop_event.set()
            button.disabled = True
            button.label = "Aborting..."
            await interaction.response.edit_message(view=self)
            self.stop()

        else:
            await interaction.response.send_message(
                f"Sorry, you do not have permission to perform this task.",
                ephemeral=True,
            )
            return


class SimpleLinkUi(discord.ui.View):
    def __init__(self, url: str):
        super().__init__()
        self.url = url

        self.add_item(
            discord.ui.Button(
                label="🔗Source", style=discord.ButtonStyle.grey, url=self.url
            )
        )
