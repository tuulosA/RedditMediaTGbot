#media_handler.py
import asyncio
import logging
import os
import aiohttp
from typing import Optional
from telegram import Update
from telegram.error import TimedOut
from asyncpraw import Reddit
from asyncpraw.models import Submission
from bot.utils.media_utils import (
    convert_gif_to_mp4,
    validate_file,
    resolve_reddit_gallery,
    determine_media_type,
    fetch_top_comment,
    cleanup_file,
    send_video
)
from bot.utils.compressor import is_file_size_valid
from bot.handle_direct_link import handle_direct_link
from bot.config import MediaConfig, RetryConfig, TimeoutConfig
from bot.utils.tempfile_utils import create_temp_dir

logger = logging.getLogger(__name__)


async def process_media_batch(
    media_list: list[Submission],
    reddit_instance: Reddit,
    update: Update,
    include_comments: bool
) -> list[Submission]:
    """
    Processes and uploads a list of media items, handling download and upload asynchronously.
    """
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_media(media, reddit_instance, update, session, include_comments) for media in media_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out successful results
    successful_media = [result for result in results if isinstance(result, Submission)]
    return successful_media


async def process_media(
    media_data: Submission,
    reddit_instance: Reddit,
    update: Update,
    session: aiohttp.ClientSession,
    include_comments: bool = False,
) -> Optional[Submission]:
    """
    Processes a single media item, downloading and uploading it asynchronously.
    """
    if not media_data.url:
        logger.warning("Media URL is missing or invalid.")
        return None

    try:
        top_comment = await fetch_top_comment(media_data) if include_comments else None
        resolved_url = await resolve_media_url(media_data.url, reddit_instance, session)
        if not resolved_url:
            return None

        # Start download and upload asynchronously
        download_task = asyncio.create_task(validate_media_download(resolved_url, session))
        upload_task = asyncio.create_task(wait_and_upload(download_task, update, top_comment))

        # Wait for upload to complete
        await upload_task

        return media_data if upload_task.result() else None
    except Exception as e:
        logger.error(f"Error processing media {media_data.url}: {e}", exc_info=True)
        return None


async def wait_and_upload(
    download_task: asyncio.Task,
    update: Update,
    caption: Optional[str]
) -> bool:
    """
    Waits for the download task to complete and uploads the file to Telegram.
    """
    try:
        file_path = await download_task
        if not file_path:
            logger.error("Download failed; skipping upload.")
            return False

        success = await send_to_telegram(file_path, update, caption=caption)
        cleanup_file(file_path)
        return success
    except Exception as e:
        logger.error(f"Error during download or upload: {e}", exc_info=True)
        return False


async def validate_media_download(resolved_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    file_path = await download_media(resolved_url, session)
    if not file_path:
        return None

    if await is_file_size_valid(file_path, MediaConfig.MAX_FILE_SIZE_MB):
        return file_path

    logger.warning(f"Invalid file size for {file_path}")
    cleanup_file(file_path)
    return None



async def resolve_media_url(media_url: str, reddit_instance: Reddit, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Resolves the final URL for media, including Reddit galleries and direct links.
    """
    try:
        if media_url.startswith("/tmp") and await validate_file(media_url):
            return media_url
        if "gallery" in media_url:
            return await resolve_reddit_gallery(media_url.split("/")[-1], reddit_instance)
        return await handle_direct_link(media_url, session)
    except Exception as e:
        logger.error(f"Error resolving media URL: {e}", exc_info=True)
        return None


async def download_media(resolved_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Downloads media from a resolved URL.
    """
    if os.path.isfile(resolved_url):
        return resolved_url if await validate_file(resolved_url) else None

    if not resolved_url.startswith(("http://", "https://")):
        logger.error(f"Invalid URL: {resolved_url}")
        return None

    temp_dir = create_temp_dir("reddit_media_")
    file_path = os.path.join(temp_dir, os.path.basename(resolved_url))

    try:
        async with session.get(resolved_url, timeout=aiohttp.ClientTimeout(total=TimeoutConfig.DOWNLOAD_TIMEOUT)) as resp:
            if resp.status == 200:
                with open(file_path, "wb") as f:
                    f.write(await resp.read())
                return await convert_gif_to_mp4(file_path) if file_path.endswith(".gif") else file_path
    except Exception as e:
        logger.error(f"Error downloading media: {e}", exc_info=True)
    cleanup_file(file_path)
    return None


async def send_to_telegram(file_path: str, update: Update, caption: Optional[str] = None) -> bool:
    """
    Sends a media file to Telegram with retry logic.
    """
    media_type = determine_media_type(file_path)
    if not media_type:
        logger.warning(f"Unsupported media type: {file_path}")
        return False

    for attempt in range(RetryConfig.RETRY_ATTEMPTS):
        try:
            if file_path.lower().endswith((".mp4", ".webm")):
                await send_video(file_path, update, caption=caption)
            else:
                await media_type(file_path, update, caption=caption)

            logger.info(f"Media sent successfully: {file_path}")
            return True
        except TimedOut:
            logger.warning(f"Timeout on attempt {attempt + 1} for {file_path}")
        except ValueError as e:
            logger.error(f"Error in video dimensions: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending file: {e}", exc_info=True)

    logger.error(f"Failed to send media after {RetryConfig.RETRY_ATTEMPTS} attempts: {file_path}")
    return False
