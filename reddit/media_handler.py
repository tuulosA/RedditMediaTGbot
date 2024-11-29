import asyncio
from telegram import Update
from telegram.error import TimedOut
import os
import logging
from typing import Optional, List
import aiohttp
from asyncpraw import Reddit
import cv2
from reddit.utils.media_utils import (
    convert_gif_to_mp4,
    validate_file,
    is_file_size_valid,
    resolve_reddit_gallery,
    determine_media_type,
    fetch_top_comment,
    cleanup_file
)
from reddit.fetch_direct_link import fetch_direct_link
from reddit.config import MediaConfig, RetryConfig, TimeoutConfig
from reddit.utils.tempfile_utils import create_temp_dir
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)


async def process_media_batch(
    media_list: List[Submission],
    reddit_instance: Reddit,
    update: Update,
    include_comments: bool
) -> List[Submission]:
    """
    Processes and uploads a list of media items.
    """
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_media(media, reddit_instance, update, session, include_comments=include_comments)
            for media in media_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    # Filter out any None results
    return [result for result in results if result]


async def process_media(
    media_data: Submission,
    reddit_instance: Reddit,
    update: Update,
    session: aiohttp.ClientSession,
    include_comments: bool = False,
) -> Optional[Submission]:
    """
    Processes a single media item: resolves URL, downloads media, validates it, and sends to Telegram.
    Handles only Submission objects.
    """
    file_path = None
    media_url = media_data.url

    if not media_url:
        logger.warning("Media URL is missing or invalid.")
        return None

    try:
        # Fetch the top human comment if include_comments is True
        top_comment = await fetch_top_comment(media_data) if include_comments else None

        # Resolve the media URL
        resolved_url = await resolve_media_url(media_url, reddit_instance, session)
        if not resolved_url:
            logger.warning(f"Failed to resolve media URL: {media_url}")
            return None

        # Download and validate the media
        file_path = await validate_media_download(resolved_url, session)
        if not file_path:
            return None

        # Send the media to Telegram
        if await send_to_telegram(file_path, update, caption=top_comment):
            return media_data  # Return the original Submission object on success
    except Exception as e:
        logger.error(f"Error processing media {media_url}: {e}", exc_info=True)
    finally:
        # Cleanup the downloaded file
        if file_path and os.path.exists(file_path):
            cleanup_file(file_path)

    return None


async def validate_media_download(resolved_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Downloads and validates a media file from a resolved URL.
    Returns the file path if valid, otherwise None.
    """
    try:
        file_path = await download_media(resolved_url, session)
        if not file_path:
            logger.warning(f"Download failed for URL: {resolved_url}")
            return None

        if not is_file_size_valid(file_path, MediaConfig.MAX_FILE_SIZE_MB):
            logger.warning(f"File size invalid or exceeds limit: {file_path}")
            cleanup_file(file_path)
            return None

        return file_path
    except Exception as e:
        logger.error(f"Error downloading or validating media from {resolved_url}: {e}", exc_info=True)
        return None


async def resolve_media_url(media_url: str, reddit_instance: Reddit, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Resolves the final URL for media, including Reddit galleries and direct links.
    """
    try:
        if media_url.startswith("/tmp") and validate_file(media_url):
            return media_url

        if "reddit.com/gallery/" in media_url:
            return await resolve_reddit_gallery(media_url.split("/")[-1], reddit_instance)

        return await fetch_direct_link(media_url, session)
    except Exception as e:
        logger.error(f"Error resolving media URL {media_url}: {e}", exc_info=True)
        return None


async def download_media(resolved_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Downloads media from a resolved URL, with optional GIF to MP4 conversion.
    """
    try:
        # Handle local file paths directly
        if os.path.isfile(resolved_url):
            logger.debug(f"Detected local file path: {resolved_url}")
            return resolved_url if validate_file(resolved_url) else None

        # Handle remote URLs
        if not resolved_url.startswith(('http://', 'https://')):
            logger.error(f"Invalid URL: {resolved_url}")
            return None

        temp_dir = create_temp_dir("reddit_media_")
        file_name = resolved_url.split("/")[-1]
        file_path = os.path.join(temp_dir, file_name)

        # Download with timeout
        # Download with timeout
        try:
            timeout = aiohttp.ClientTimeout(total=TimeoutConfig.DOWNLOAD_TIMEOUT)
            async with session.get(resolved_url, timeout=timeout) as response:
                if response.status != 200:
                    logger.error(f"Failed to download media. HTTP Status: {response.status}, URL: {resolved_url}")
                    return None

                file_content = await response.read()
                with open(file_path, "wb") as f:
                    f.write(file_content)
        except asyncio.TimeoutError:
            logger.error(f"Download timed out for URL: {resolved_url}")
            return None

        # Validate and process the downloaded file
        if validate_file(file_path):
            if file_path.endswith(".gif"):
                return await convert_gif_to_mp4(file_path)
            return file_path
        else:
            os.remove(file_path)
            return None
    except Exception as e:
        logger.error(f"Error downloading media from {resolved_url}: {e}", exc_info=True)
        return None


async def send_to_telegram(file_path: str, update: Update, caption: Optional[str] = None) -> bool:
    """
    Sends a media file to Telegram with retry logic.
    """
    media_type = determine_media_type(file_path)
    if not media_type:
        logger.warning(f"Unsupported media type: {file_path}")
        return False

    bot = update.get_bot()

    if file_path.endswith(("mp4", "webm")):
        return await send_video(file_path, bot, update, caption)

    # Retry logic for non-video media
    for attempt in range(1, RetryConfig.RETRY_ATTEMPTS + 1):
        try:
            await media_type(file_path, update, caption=caption)
            logger.info(f"Media sent successfully: {file_path}")
            return True
        except TimedOut as e:
            logger.warning(f"Timeout on attempt {attempt} for {file_path}: {e}")
            if attempt < RetryConfig.RETRY_ATTEMPTS:
                await asyncio.sleep(RetryConfig.RETRY_DELAY)
            else:
                logger.error(f"Failed to send media after {RetryConfig.RETRY_ATTEMPTS} attempts: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error sending file {file_path} to Telegram: {e}", exc_info=True)
            return False
    return False


async def send_video(file_path: str, bot, update: Update, caption: Optional[str] = None) -> bool:
    """
    Handles sending video files to Telegram with resolution metadata and optional caption.
    Retries on timeout errors.
    """
    cap = None  # Initialize cap to avoid referencing before assignment

    for attempt in range(1, RetryConfig.RETRY_ATTEMPTS + 1):
        try:
            cap = cv2.VideoCapture(file_path)
            width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if not (width and height):
                logger.error(f"Invalid video dimensions for file: {file_path}")
                return False

            with open(file_path, "rb") as video_file:
                # Send the video without the `timeout` argument
                await bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=video_file,
                    width=width,
                    height=height,
                    supports_streaming=True,
                    caption=caption
                )
            logger.info(f"Video successfully sent: {file_path}")
            return True
        except TimedOut as e:
            logger.warning(f"Timeout on attempt {attempt} for video {file_path}: {e}")
            if attempt < RetryConfig.RETRY_ATTEMPTS:
                await asyncio.sleep(RetryConfig.RETRY_DELAY)
            else:
                logger.error(f"Failed to send video after {RetryConfig.RETRY_ATTEMPTS} attempts: {file_path}")
                return False
        except Exception as e:
            logger.error(f"Error sending video {file_path}: {e}", exc_info=True)
            return False
        finally:
            if cap:  # Ensure cap is released only if it was successfully initialized
                cap.release()
    return False