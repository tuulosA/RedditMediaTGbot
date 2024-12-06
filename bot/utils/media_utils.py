#media_utils.py
import os
import logging
import random
import subprocess
from typing import Optional
from asyncpraw import Reddit
from asyncpraw.models import Submission
from urllib.parse import urlparse
import asyncio

logger = logging.getLogger(__name__)


async def convert_gif_to_mp4(gif_path: str) -> Optional[str]:
    """
    Converts a GIF file to MP4 using FFmpeg.
    """
    if not await validate_file(gif_path):
        logger.error(f"File not found for conversion: {gif_path}")
        return None

    mp4_path = gif_path.replace(".gif", ".mp4")
    command = [
        "ffmpeg", "-y", "-i", gif_path,
        "-movflags", "faststart",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
        mp4_path,
    ]

    try:
        logger.info(f"Converting GIF to MP4: {gif_path} -> {mp4_path}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            logger.info(f"Successfully converted GIF to MP4: {mp4_path}")
            cleanup_file(gif_path)
            return mp4_path

        logger.error(f"FFmpeg error: {result.stderr.decode()}")
    except Exception as e:
        logger.error(f"Error during GIF to MP4 conversion: {e}", exc_info=True)
    return None


def determine_media_type(file_path: str):
    """
    Determines the media type based on file extension.
    """
    file_extension = os.path.splitext(urlparse(file_path).path)[1].lower()

    if file_extension in (".mp4", ".webm"):
        return lambda fp, upd, caption=None: asyncio.run_coroutine_threadsafe(
            send_video(fp, upd, caption), asyncio.get_event_loop()
        )
    elif file_extension in (".jpg", ".jpeg", ".png"):
        return lambda fp, upd, caption=None: asyncio.run_coroutine_threadsafe(
            send_photo(fp, upd, caption), asyncio.get_event_loop()
        )
    elif file_extension == ".gif":
        return lambda fp, upd, caption=None: asyncio.run_coroutine_threadsafe(
            send_animation(fp, upd, caption), asyncio.get_event_loop()
        )

    logger.warning(f"Unsupported media type for file: {file_path}")
    return None


async def send_video(file_path, update, caption=None):
    with open(file_path, "rb") as video_file:
        await update.message.reply_video(
            video=video_file,
            supports_streaming=True,
            caption=caption
        )


async def send_photo(file_path, update, caption=None):
    with open(file_path, "rb") as photo_file:
        await update.message.reply_photo(photo=photo_file, caption=caption)


async def send_animation(file_path, update, caption=None):
    with open(file_path, "rb") as animation_file:
        await update.message.reply_animation(animation=animation_file, caption=caption)


async def validate_file(file_path: str) -> bool:
    """
    Asynchronously validates a file by checking its existence and non-zero size.
    """
    def file_check():
        return os.path.exists(file_path) and os.path.getsize(file_path) > 0

    is_valid = await asyncio.to_thread(file_check)
    if is_valid:
        logger.info(f"File validated: {file_path}")
    else:
        logger.warning(f"Invalid file: {file_path}")
    return is_valid


def cleanup_file(file_path: str) -> None:
    """
    Deletes a file and its parent directory if empty.
    """
    if not file_path:
        return
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
        parent_dir = os.path.dirname(file_path)
        if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
            os.rmdir(parent_dir)
    except Exception as e:
        logger.error(f"Error cleaning up file: {file_path}, {e}", exc_info=True)


async def resolve_reddit_gallery(post_id: str, reddit_instance: Reddit) -> Optional[str]:
    """
    Resolves a random media URL from a Reddit gallery post.
    """
    try:
        submission = await reddit_instance.submission(id=post_id)
        media_urls = [
            item["s"]["u"].replace("&amp;", "&")
            for item in submission.media_metadata.values()
            if "s" in item and "u" in item["s"]
        ]
        return random.choice(media_urls) if media_urls else None
    except Exception as e:
        logger.error(f"Error resolving gallery: {e}", exc_info=True)
        return None


async def fetch_top_comment(media_data: Submission) -> Optional[str]:
    """
    Fetches the top human-readable comment for a submission.
    """
    try:
        await media_data.comments()
        for comment in media_data.comments.list():
            if comment.body and not any(kw in comment.body.lower() for kw in ["http", "www", ".com", "[deleted]", "sauce", "[removed]", "u/", "source"]):
                return comment.body
    except Exception as e:
        logger.warning(f"Failed to fetch comment: {e}")
    return None
