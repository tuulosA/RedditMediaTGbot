from asyncpraw.models import Submission
import os
import logging
import random
import subprocess
from typing import Optional
from asyncpraw import Reddit
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def is_file_size_valid(file_path: str, max_size_mb: int) -> bool:
    """
    Checks if a file's size is within the specified maximum size in MB.
    """
    if not validate_file(file_path):
        return False

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        logger.debug(f"File size is valid: {file_size_mb:.2f} MB <= {max_size_mb} MB")
        return True

    logger.warning(f"File size exceeds limit: {file_size_mb:.2f} MB > {max_size_mb} MB")
    return False


async def convert_gif_to_mp4(gif_path: str) -> Optional[str]:
    """
    Converts a GIF file to MP4 using FFmpeg.
    """
    if not validate_file(gif_path):
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
        return lambda fp, upd, caption=None: upd.message.reply_video(
            video=open(fp, "rb"), supports_streaming=True, caption=caption
        )
    elif file_extension in (".jpg", ".jpeg", ".png"):
        return lambda fp, upd, caption=None: upd.message.reply_photo(photo=open(fp, "rb"), caption=caption)
    elif file_extension == ".gif":
        return lambda fp, upd, caption=None: upd.message.reply_animation(animation=open(fp, "rb"), caption=caption)

    logger.warning(f"Unsupported media type for file: {file_path}")
    return None


def validate_file(file_path: str) -> bool:
    """
    Validates a file by checking its existence and non-zero size.
    """
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        logger.info(f"File validated: {file_path}")
        return True
    logger.warning(f"Invalid file: {file_path}")
    return False


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
            if comment.body and not any(kw in comment.body.lower() for kw in ["http", "www", "[deleted]"]):
                return comment.body
    except Exception as e:
        logger.warning(f"Failed to fetch comment: {e}")
    return None
