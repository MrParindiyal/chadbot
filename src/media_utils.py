from aiolimiter import AsyncLimiter
import asyncio
import discord
import glob
import json
import logging
import os
from src.config import EMOJIS
from src.utils import run_cmd_cancellable, CancelButtonUi, SimpleLinkUi
from typing import Callable, Awaitable
import urllib.parse
import yt_dlp
from yt_dlp.utils import DownloadError

logger = logging.getLogger(__name__)

ratelimiter = AsyncLimiter(5, 60)

def download_ig_media(
    url: str,
    uid: int,
    interactionid: int,
    stop_event: asyncio.Event | None,
    output_dir: str = "./data/downloads/raw",
) -> dict:

    os.makedirs(output_dir, exist_ok=True)
    parsed_url = urllib.parse.urlparse(url)
    query_param = urllib.parse.parse_qs(parsed_url.query)
    target_index = query_param.get("img_index", ["1"])[0]

    def _cancel_hook(d):
        if stop_event and stop_event.is_set():
            raise DownloadError("ABORTED_BY_USER")

    ydl_opts = {
        "outtmpl": os.path.join(output_dir, f"{uid}_%(id).8s_{interactionid}.%(ext)s"),
        "format": "bv*+ba/b",  # best audio + video, or single best stream
        "merge_output_format": "mp4",  # merge separate streams into MP4 when possible.
        "ffmpeg_location": "/usr/local/bin/ffmpeg",  # path to ffmpeg bin
        "quiet": True,
        "no_warnings": True,
        "playlist_items": target_index,
        "extractor_args": {"generic": {"impersonate": ["chrome"]}},
        "progress_hooks": [_cancel_hook],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if info and "entries" in info:
                entries = [entry for entry in info["entries"] if entry != None]
                if entries == None:
                    return {
                        "success": False,
                        "error": f"Slide {target_index} could not be found or downloaded.",
                    }
                info = entries[0]

            # This gives you the actual requested output filename,
            # accounting for yt-dlp's post-processing.
            filename = ydl.prepare_filename(info)

            # If video+audio were merged, prepare_filename() can still
            # contain the original video extension, so check alternatives.
            base, _ = os.path.splitext(filename)

            possible_files = [
                filename,
                base + ".mp4",
                base + ".mkv",
                base + ".webm",
            ]

            final_filename = next(
                (path for path in possible_files if os.path.exists(path)), None
            )

            if not final_filename:
                return {
                    "success": False,
                    "error": "Download completed but output file could not be located.",
                }

            ext = os.path.splitext(final_filename)[1].lower().lstrip(".")

            media_type = "video" if ext in {"mp4", "mkv", "webm", "mov"} else ext

            return {
                "success": True,
                "file_path": final_filename,
                "media_type": media_type,
                "extension": ext,
            }

    except Exception as e:
        for part_file in glob.glob(
            os.path.join(output_dir, f"{uid}_*_{interactionid}*")
        ):
            try:
                os.remove(part_file)
            except OSError:
                pass
        if "ABORTED_BY_USER" in str(e):
            return {"success": False, "aborted": True, "error": "Aborted by user"}
        return {"success": False, "aborted": False, "error": str(e)}


async def compressor(
    input_file: str,
    target_size=19.6,
    output_file="./data/downloads/compressed/out_compressed.mp4",
    stop_event: asyncio.Event | None = None,
) -> str:
    async with ratelimiter:
        os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

        # turn off black formatter for this block
        # fmt: off
        probe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "format=duration:stream=width,height",
            "-select_streams", "v:0",
            "-of", "json",
            input_file,
        ]
        #fmt: on

        probe_output = await run_cmd_cancellable(
            probe_cmd, stop_event=stop_event, capture_stdout=True
        )
        probe_data = json.loads(probe_output.decode("utf-8"))

        video_info = probe_data["streams"][0]
        width = video_info["width"]
        height = video_info["height"]

        duration = float(probe_data["format"]["duration"])

        total_bits = target_size * 1024 * 1024 * 8 * 0.96  # container overhead margin ~4.5%
        total_bitrate = int(total_bits / duration)
        audio_bitrate = 64 if total_bitrate < 350_000 else 96
        video_bitrate = max(64_000, total_bitrate - (audio_bitrate * 1000))

        max_dim = max(width, height)
        scale_filter = ""

        # Downscale only when bitrate per pixel would produce severe compression artifacts
        if video_bitrate < 400_000 and max_dim > 720:
            scale_filter = "scale=w=720:h=720:force_original_aspect_ratio=decrease,"
        elif video_bitrate < 1_200_000 and max_dim > 1080:
            scale_filter = "scale=w=1080:h=1080:force_original_aspect_ratio=decrease,"

        v_filter = f"{scale_filter}pad=ceil(iw/2)*2:ceil(ih/2)*2,format=yuv420p"

        passlog_prefix = os.path.splitext(os.path.abspath(output_file))[0] + "_2pass"

        # turn off black formatter for this block
        # fmt: off
        pass1_cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-c:v", "libx264",
            "-b:v", str(video_bitrate),
            "-maxrate", f"{int(video_bitrate * 1.2 // 1000)}k",
            "-bufsize", f"{int(video_bitrate * 1.2 // 1000)}k",
            "-preset", "veryfast",
            "-vf", v_filter,
            "-threads", "0", 
            "-pass", "1",
            "-passlogfile", passlog_prefix,
            "-an", "-f",
            "null", os.devnull,
            "-v", "error",
            "-hide_banner", "-stats"
        ]

        pass2_cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-c:v", "libx264",
            "-b:v", str(video_bitrate),
            "-maxrate", f"{int(video_bitrate * 1.2 // 1000)}k",
            "-bufsize", f"{int(video_bitrate * 1.2 // 1000)}k",
            "-preset", "veryfast",
            "-vf", v_filter,
            "-threads", "0",
            "-pass", "2",
            "-passlogfile", passlog_prefix,
            "-c:a", "aac",
            "-b:a", f"{audio_bitrate}k",
            "-fs", f"{int(target_size * 1024*1024*0.96)}",
            "-v", "error",
            "-hide_banner", "-stats",
            output_file,
        ]
        #fmt: on
        try:
            await run_cmd_cancellable(pass1_cmd, stop_event=stop_event)
            await run_cmd_cancellable(pass2_cmd, stop_event=stop_event)

        except asyncio.CancelledError:
            # Remove half-written output file if cancelled during pass 2
            if os.path.exists(output_file):
                os.remove(output_file)
            raise

        finally:
            for ext in ["-0.log", "-0.log.mbtree", "-0.log.temp", "-0.log.mbtree.temp"]:
                log_file = f"{passlog_prefix}{ext}"
                if os.path.exists(log_file):
                    os.remove(log_file)

        return output_file


async def bg_extractor(interaction: discord.Interaction, url: str):
    stop_event = asyncio.Event()
    cancel_view = CancelButtonUi(interaction.user.id, stop_event, url)

    await interaction.edit_original_response(
        content=f"{EMOJIS["loading"]} Downloading request...", view=cancel_view
    )

    async def notify_compression():
        await interaction.edit_original_response(
            content=f"{EMOJIS["catJam"]} File too big, compressing... {EMOJIS["loading"]}",
            view=cancel_view,
        )

    raw_file, final_file = None, None

    try:
        final_file, raw_file = await download_and_compress(
            url=url,
            uid=interaction.user.id,
            req_id=interaction.id,
            stop_event=stop_event,
            on_compress_start=notify_compression,
            timeout=180,
        )

        await interaction.edit_original_response(
            content=None, attachments=[discord.File(final_file)], view=SimpleLinkUi(url)
        )

    except asyncio.CancelledError:
        logger.warning(
            f"Task aborted! By @{interaction.user.display_name} in {interaction.guild.name} #{interaction.channel.name}"
        )
        await interaction.edit_original_response(
            content=f":warning: Task aborted by user.",
            view=SimpleLinkUi(url),
        )

    except asyncio.TimeoutError:
        logger.warning(
            f"Compressor timed out! {url} by @{interaction.user.display_name} in {interaction.guild.name} #{interaction.channel.name}"
        )
        await interaction.edit_original_response(
            content=f":x: Compressor timed out", view=SimpleLinkUi(url)
        )

    except Exception as e:
        logger.exception(f"Failed to send the file. {str(e)[:100]}")
        await interaction.edit_original_response(
            content=f":x: Processing Failed :( {str(e)[:75]}", view=SimpleLinkUi(url)
        )

    finally:
        for path in {raw_file, final_file}:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except FileNotFoundError:
                    pass

    # result = await asyncio.to_thread(
    #     download_ig_media, url, interaction.user.id, interaction.id
    # )

    # if not result["success"]:
    #     logger.warning(
    #         f"{interaction.user} used /insta link:{url} => {result["error"]}"
    #     )
    #     await interaction.delete_original_response()
    #     await interaction.channel.send(
    #         content=f"""
    #             :x: {interaction.user.mention} Failed to process request : {result["error"][:100]}...
    #             \nHere's the source URL : {url}
    #         """,
    #     )
    #     return

    # file_path = result["file_path"]
    # file_size = os.path.getsize(file_path) / (1024 * 1024)

    # if file_size < 20:
    #     final_file = file_path
    # else:
    #     stop_event = asyncio.Event()
    #     cancel_view = CancelButtonUi(interaction.user.id, stop_event, url)
    #     await interaction.edit_original_response(
    #         content=f"{EMOJIS["catJam"]} File too big, compressing... {EMOJIS["loading"]}",
    #         view=cancel_view,
    #     )

    #     file_name = "_".join(
    #         str(os.path.basename(file_path)).removesuffix(".mp4").split("_")[1:-1]
    #     )
    #     output_file_path = f"./data/downloads/compressed/{interaction.user.id}_{file_name}.compressed_{interaction.id}.mp4"

    #     try:
    #         final_file = await asyncio.wait_for(
    #             compressor(
    #                 file_path, output_file=output_file_path, stop_event=stop_event
    #             ),
    #             timeout=180,
    #         )
    #     except asyncio.TimeoutError:
    #         logger.warning(
    #             f"Compressor timed out! {url} by @{interaction.user.display_name} in {interaction.guild.name} #{interaction.channel.name}"
    #         )
    #         await interaction.edit_original_response(
    #             content=f":x: Compressor timed out", view=SimpleLinkUi(url)
    #         )
    #         os.remove(file_path)
    #     except asyncio.CancelledError:
    #         logger.warning(
    #             f"Compression aborted! By @{interaction.user.display_name} in {interaction.guild.name} #{interaction.channel.name}"
    #         )
    #         await interaction.edit_original_response(
    #             content=f":warning: Compression aborted by user.",
    #             view=SimpleLinkUi(url),
    #         )

    # try:
    #     await interaction.edit_original_response(
    #         content=None, attachments=[discord.File(final_file)], view=SimpleLinkUi(url)
    #     )
    # except Exception as e:
    #     logger.exception(
    #         f"Failed to send the file. RawSize:{file_size:.2f}MB | CompressedSize:{(os.path.getsize(final_file) / (1024 * 1024)):.2f}MB"
    #     )
    #     await interaction.edit_original_response(
    #         content=f":x: Processing Failed :( {str(e)[:75]}"
    #     )
    # finally:
    #     for path in {file_path, final_file}:
    #         try:
    #             os.remove(path)
    #         except FileNotFoundError:
    #             pass


async def download_and_compress(
    url: str,
    uid: int,
    req_id: int,
    stop_event: asyncio.Event,
    on_compress_start: Callable[[], Awaitable[None]],
    timeout: float = 180,
) -> tuple[str | None, str | None]:
    raw_file = None

    async def _pipeline():
        nonlocal raw_file

        result = await asyncio.to_thread(
            download_ig_media, url, uid, req_id, stop_event
        )

        if result.get("aborted") or stop_event.is_set():
            raise asyncio.CancelledError("Download aborted by user")

        if not result["success"]:
            raise RuntimeError(result["error"])

        raw_file = result["file_path"]
        file_size = os.path.getsize(raw_file) / (1024 * 1024)

        if file_size < 20:
            return raw_file, raw_file

        await on_compress_start()

        file_name = "_".join(
            str(os.path.basename(raw_file)).removesuffix(".mp4").split("_")[1:-1]
        )
        output_file_path = (
            f"./data/downloads/compressed/{uid}_{file_name}.compressed_{req_id}.mp4"
        )

        compressed_file = await compressor(
            raw_file, output_file=output_file_path, stop_event=stop_event
        )
        return compressed_file, raw_file

    try:
        return await asyncio.wait_for(_pipeline(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        stop_event.set()

        if raw_file and os.path.exists(raw_file):
            os.remove(raw_file)
        raise
