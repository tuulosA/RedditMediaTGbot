import os
import logging
import subprocess
import random
from typing import Optional
from asyncpraw import Reddit
from urllib.parse import urlparse
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)


async def convert_gif_to_mp4(gif_path: str) -> Optional[str]:
    """
    Converts a GIF file to MP4 using FFmpeg.
    """
    if not os.path.exists(gif_path):
        logger.error(f"File not found for conversion: {gif_path}")
        return None

    mp4_path = gif_path.replace(".gif", ".mp4")
    command = [
        "ffmpeg", "-y",
        "-i", gif_path,
        "-movflags", "faststart",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",  # Ensure even dimensions
        mp4_path,
    ]

    try:
        logger.info(f"Running FFmpeg command: {' '.join(command)}")
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode == 0:
            logger.info(f"Successfully converted GIF to MP4: {mp4_path}")
            cleanup_file(gif_path)
            return mp4_path
        else:
            logger.error(f"FFmpeg error while converting {gif_path} to MP4: {result.stderr.decode()}")
            return None
    except Exception as e:
        logger.error(f"Error converting GIF to MP4: {gif_path}. Exception: {e}", exc_info=True)
        return None


def validate_file(file_path: str) -> bool:
    """
    Validates a file by checking its existence and non-zero size.
    """
    if not os.path.exists(file_path):
        logger.warning(f"Validation failed: File does not exist: {file_path}")
        return False

    if os.path.getsize(file_path) > 0:
        logger.info(f"File validation successful: {file_path}")
        return True

    logger.warning(f"Validation failed: File is empty: {file_path}")
    return False


def determine_media_type(file_path: str):
    """
    Determines the media type (video, photo, or animation) based on the file extension.
    Sanitizes the file path by stripping query parameters before determining the media type.
    Supports optional captions.
    """

    logger.debug(f"Determining media type for file: {file_path}")

    # Strip query parameters and fragments
    sanitized_path = urlparse(file_path).path
    file_extension = os.path.splitext(sanitized_path)[1].lower()  # Extract and normalize the extension

    if file_extension in (".mp4", ".webm"):
        return lambda fp, upd, caption=None: upd.message.reply_video(
            video=open(fp, "rb"), supports_streaming=True, caption=caption
        )
    elif file_extension in (".jpg", ".jpeg", ".png"):
        return lambda fp, upd, caption=None: upd.message.reply_photo(photo=open(fp, "rb"), caption=caption)
    elif file_extension == ".gif":
        return lambda fp, upd, caption=None: upd.message.reply_animation(animation=open(fp, "rb"), caption=caption)

    logger.warning(f"Unsupported media type for file: {file_path} (sanitized path: {sanitized_path})")
    return None


def cleanup_file(file_path: str) -> None:
    """
    Deletes a file if it exists and removes the parent directory if empty.
    """
    if not file_path:
        logger.warning("No file path provided for cleanup.")
        return

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"File cleaned up: {file_path}")

        parent_dir = os.path.dirname(file_path)
        if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
            os.rmdir(parent_dir)
            logger.info(f"Empty directory cleaned up: {parent_dir}")
    except Exception as e:
        logger.error(f"Failed to clean up file or directory: {file_path}. Exception: {e}", exc_info=True)


def is_file_size_valid(file_path: str, max_size_mb: int, compress: bool = True) -> bool:
    """
    Checks if a file's size is within the specified maximum size in MB.
    If the file exceeds the size limit and compression is enabled, attempts to compress it.
    """
    if not os.path.exists(file_path):
        logger.warning(f"File does not exist for size validation: {file_path}")
        return False

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        logger.debug(f"File size validation passed: {file_size_mb:.2f} MB <= {max_size_mb} MB")
        return True

    logger.warning(f"File size exceeds limit: {file_size_mb:.2f} MB > {max_size_mb} MB")
    if compress:
        compressed_path = os.path.splitext(file_path)[0] + "_compressed.mp4"
        if compress_video(file_path, compressed_path, target_size_mb=max_size_mb):
            os.replace(compressed_path, file_path)  # Replace original with compressed
            return True

    return False


def compress_video(input_path: str, output_path: str, target_size_mb: int = 50, max_attempts: int = 3) -> bool:
    """
    Compresses a video to ensure it is below the specified size limit.

    Args:
        input_path (str): Path to the input video file.
        output_path (str): Path to save the compressed video.
        target_size_mb (int): Target size in MB for the compressed video.
        max_attempts (int): Maximum number of compression attempts.

    Returns:
        bool: True if compression is successful and the output file meets the size requirement, False otherwise.
    """
    crf = 36  # Starting compression factor
    max_bitrate = 2000  # Starting bitrate (in kbps)

    for attempt in range(max_attempts):
        try:
            logger.info(f"Compression attempt {attempt + 1} for {input_path} with CRF={crf}, Max Bitrate={max_bitrate}")
            command = [
                "ffmpeg",
                "-i", input_path,
                "-vcodec", "libx264",
                "-crf", str(crf),
                "-preset", "medium",
                "-b:v", f"{max_bitrate}k",  # Adjust bitrate
                "-vf", "scale=1280:-2",  # Downscale to 720p if needed
                "-acodec", "aac",
                "-b:a", "128k",
                output_path,
            ]

            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            if compressed_size_mb <= target_size_mb:
                logger.info(f"Compression successful: {compressed_size_mb:.2f} MB <= {target_size_mb} MB")
                cleanup_file(input_path)
                return True
            else:
                logger.warning(f"Compressed file exceeds size limit: {compressed_size_mb:.2f} MB > {target_size_mb} MB")
                cleanup_file(output_path)
        except Exception as e:
            logger.error(f"Error during compression attempt {attempt + 1}: {e}", exc_info=True)

        # Adjust parameters for the next attempt
        crf += 2
        max_bitrate -= 500

    logger.error(f"Failed to compress {input_path} below {target_size_mb} MB after {max_attempts} attempts.")
    return False


async def resolve_reddit_gallery(post_id: str, reddit_instance: Reddit) -> Optional[str]:
    """
    Resolves a random media URL from a Reddit gallery post.

    Args:
        post_id (str): ID of the Reddit gallery post.
        reddit_instance (Reddit): Reddit API client instance.

    Returns:
        Optional[str]: Resolved media URL, or None if no valid media is found.
    """
    try:
        submission = await reddit_instance.submission(id=post_id)

        if not hasattr(submission, "media_metadata"):
            logger.warning(f"No media metadata found for gallery post: {post_id}")
            return None

        # Extract media URLs from metadata
        media_urls = [
            item["s"]["u"].replace("&amp;", "&")
            for item in submission.media_metadata.values()
            if "s" in item and "u" in item["s"]
        ]

        if media_urls:
            random_url = random.choice(media_urls)
            logger.debug(f"Selected random URL from gallery: {random_url}")
            return random_url

        logger.warning(f"No media URLs found for gallery post: {post_id}")
        return None

    except Exception as e:
        logger.error(f"Error resolving Reddit gallery {post_id}: {e}", exc_info=True)
        return None


async def fetch_top_comment(media_data: Submission) -> Optional[str]:
    """
    Fetches the top human-readable comment for a submission.
    Skips comments with links, deleted content, or common irrelevant patterns.
    """
    try:
        await media_data.comments()  # Load comments for the specific post
        filters = ["http", "www", ".com", "[deleted]", "sauce", "[removed]", "u/", "source"]

        for comment in media_data.comments.list():
            if comment.body and not any(keyword in comment.body.lower() for keyword in filters):
                logger.info(f"Selected top comment for post ID {media_data.id}: {comment.body}")
                return comment.body
        logger.info(f"No suitable top comment found for post ID {media_data.id}.")
    except Exception as e:
        logger.warning(f"Failed to fetch top comment for post ID {media_data.id}: {e}")
    return None


