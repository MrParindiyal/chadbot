import asyncio
from src.config import EMOJIS
import discord
import json
import logging
import os
import ratelimit
import subprocess
import urllib.parse
import yt_dlp

logger = logging.getLogger(__name__)


def download_ig_media(
    url: str, uid: int, interactionid: int, output_dir: str = "./data/downloads/raw"
) -> dict:

    os.makedirs(output_dir, exist_ok=True)

    parsed_url = urllib.parse.urlparse(url)
    query_param = urllib.parse.parse_qs(parsed_url.query)
    target_index = query_param.get("img_index", ["1"])[0]

    ydl_opts = {
        "outtmpl": os.path.join(output_dir, f"{uid}_%(id)s_{interactionid}.%(ext)s"),
        "format": "bv*+ba/b",  # best audio + video, or single best stream
        "merge_output_format": "mp4",  # merge separate streams into MP4 when possible.
        "ffmpeg_location": "/usr/local/bin/ffmpeg",  # path to ffmpeg bin
        "quiet": True,
        "no_warnings": True,
        "playlist_items": target_index,
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
        return {"success": False, "error": str(e)}


@ratelimit.limits(calls=4, period=60)
def compressor(
    input_file: str,
    target_size=9.6,
    output_file="./data/downloads/compressed/out_compressed.mp4",
) -> str:

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

    probe_output = subprocess.check_output(probe_cmd).decode("utf-8")
    probe_data = json.loads(probe_output)
    print(probe_data)

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
        subprocess.run(pass1_cmd, check=True)
        subprocess.run(pass2_cmd, check=True)

    finally:
        for log_file in [f"{passlog_prefix}-0.log", f"{passlog_prefix}-0.log.mbtree"]:
            if os.path.exists(log_file):
                os.remove(log_file)

    return output_file


async def bg_extractor(interaction: discord.Interaction, url: str):
    await interaction.edit_original_response(
        content=f"{EMOJIS["loading"]} Downloading request..."
    )
    result = await asyncio.to_thread(
        download_ig_media, url, interaction.user.id, interaction.id
    )

    if not result["success"]:
        logger.warning(
            f"{interaction.user} used /insta link:{url} => {result["error"]}"
        )
        await interaction.delete_original_response()
        await interaction.channel.send(
            content=f":x: {interaction.user.mention} Failed to process request : {result["error"][:100]}",
        )
        return

    file_path = result["file_path"]
    file_size = os.path.getsize(file_path) / (1024 * 1024)

    if file_size < 10:
        final_file = file_path
    else:
        await interaction.edit_original_response(
            content=f"{EMOJIS["catJam"]} File too big, compressing... (will take ~duration of the media)"
        )
        file_name = "_".join(
            str(os.path.basename(file_path)).removesuffix(".mp4").split("_")[1:-1]
        )
        final_file = await asyncio.to_thread(
            compressor,
            file_path,
            output_file=f"./data/downloads/compressed/{interaction.user.id}_{file_name}.compressed_{interaction.id}.mp4",
        )

    try:
        await interaction.edit_original_response(
            content=None, attachments=[discord.File(final_file)]
        )
    except Exception as e:
        logger.exception(
            f"Failed to send the file. RawSize:{file_size:.2f}MB | CompressedSize:{(os.path.getsize(final_file) / (1024 * 1024)):.2f}MB"
        )
        await interaction.edit_original_response(
            content=f":x: Processing Failed :( {str(e)[:75]}"
        )
    finally:
        for path in {file_path, final_file}:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
