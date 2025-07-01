# Updated media_handler.py to use Compressor class for size validation

import asyncio
import logging
import aiohttp

from typing import Optional
from telegram import Update
from telegram.error import TimedOut
from asyncpraw import Reddit
from asyncpraw.models import Submission

from redditcommand.config import MediaConfig, RetryConfig
from redditcommand.utils.media_utils import MediaSender, MediaUtils, MediaDownloader
from redditcommand.utils.compressor import Compressor
from redditcommand.utils.tempfile_utils import TempFileManager

from redditcommand.handle_direct_link import handle_direct_link

logger = logging.getLogger(__name__)


async def process_media_batch(
    media_list: list[Submission],
    reddit_instance: Reddit,
    update: Update,
    include_comments: bool,
    include_flair: bool,
    include_title: bool
) -> list[Submission]:
    async with aiohttp.ClientSession() as session:
        tasks = [
            process_single_media(
                media, reddit_instance, update, session,
                include_comments, include_flair, include_title
            )
            for media in media_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return [result for result in results if isinstance(result, Submission)]


async def process_single_media(
    media: Submission,
    reddit: Reddit,
    update: Update,
    session: aiohttp.ClientSession,
    include_comments: bool = False,
    include_flair: bool = False,
    include_title: bool = False,
) -> Optional[Submission]:
    if not media.url:
        logger.warning("Media URL is missing or invalid.")
        return None

    try:
        # Compose caption in correct order
        caption_parts = []
        if include_title and media.title:
            caption_parts.append(f"{media.title.strip()}")
        if include_flair and media.link_flair_text:
            caption_parts.append(f"[{media.link_flair_text.strip()}]")
        if include_comments:
            top_comment = await MediaUtils.fetch_top_comment(media)
            if top_comment:
                caption_parts.append(f"💬 {top_comment.strip()}")

        caption = "\n".join(part for part in caption_parts if part) or None
        if caption and len(caption) > 1024:
            logger.warning(f"Caption too long ({len(caption)} characters), truncating to 1024.")
            caption = caption[:1021] + "…"

        resolved_url = await resolve_media_url(media, reddit, session)
        if not resolved_url:
            return None

        file_path = await download_and_validate_media(resolved_url, session, post_id=media.id)
        if not file_path:
            return None

        if await upload_media_to_telegram(file_path, update, caption):
            return media

    except Exception as e:
        logger.error(f"Error processing media {media.url}: {e}", exc_info=True)

    return None


async def resolve_media_url(post: Submission, reddit: Reddit, session: aiohttp.ClientSession) -> Optional[str]:
    try:
        media_url = post.url

        # If it's a temp file path, validate and return
        if media_url.startswith("/tmp") and await MediaUtils.validate_file(media_url):
            return media_url

        # Handle Reddit gallery posts
        if "gallery" in media_url:
            return await MediaUtils.resolve_reddit_gallery(media_url.split("/")[-1], reddit)

        # Delegate to the direct link handler with full Reddit post context
        return await handle_direct_link(media_url, session, post=post)

    except Exception as e:
        logger.error(f"Error resolving media URL for post {post.id}: {e}", exc_info=True)
        return None


async def download_and_validate_media(
    resolved_url: str,
    session: aiohttp.ClientSession,
    post_id: Optional[str] = None
) -> Optional[str]:
    file_path = await download_media_file(resolved_url, session, post_id=post_id)
    if not file_path:
        return None

    if await Compressor.is_valid(file_path, MediaConfig.MAX_FILE_SIZE_MB):
        return file_path

    logger.warning(f"File too large after download: {file_path}")
    TempFileManager.cleanup_file(file_path)
    return None


async def download_media_file(
    resolved_url: str,
    session: aiohttp.ClientSession,
    post_id: Optional[str] = None
) -> Optional[str]:
    import os
    import urllib.parse

    # Local file path (already downloaded)
    if os.path.isfile(resolved_url):
        if await MediaUtils.validate_file(resolved_url):
            logger.info(f"Resolved to valid local file: {resolved_url}")
            return resolved_url
        else:
            logger.warning(f"Local file invalid or empty: {resolved_url}")
            return None

    if not resolved_url.startswith(("http://", "https://")):
        logger.debug(f"Skipping download: resolved path is not a URL and not a file: {resolved_url}")
        return resolved_url if await MediaUtils.validate_file(resolved_url) else None

    temp_dir = TempFileManager.create_temp_dir("reddit_media_")
    cleaned_path = urllib.parse.urlparse(resolved_url).path
    ext = os.path.splitext(cleaned_path)[1]
    if not ext or ext == ".":
        ext = ".mp4"
    final_id = post_id or TempFileManager.extract_post_id_from_url(resolved_url) or "unknown"
    file_path = os.path.join(temp_dir, f"reddit_{final_id}{ext}")

    file_path = await MediaDownloader.download_file(resolved_url, file_path, session)

    if file_path and file_path.endswith(".gif"):
        converted = await MediaUtils.convert_gif_to_mp4(file_path)
        TempFileManager.cleanup_file(file_path)
        return converted

    return file_path


async def upload_media_to_telegram(file_path: str, target, caption: Optional[str]) -> bool:
    media_handler = MediaSender.determine_type(file_path)
    if not media_handler:
        logger.warning(f"Unsupported media type: {file_path}")
        return False

    for attempt in range(RetryConfig.RETRY_ATTEMPTS):
        try:
            # Always delegate to correct media handler
            await media_handler(file_path, target, caption=caption)

            logger.info(f"Successfully sent media: {file_path}")
            TempFileManager.cleanup_file(file_path)
            return True

        except TimedOut:
            logger.warning(f"Timed out on attempt {attempt + 1} for file: {file_path}")
            TempFileManager.cleanup_file(file_path)
            return True

        except Exception as e:
            logger.error(f"Upload failed on attempt {attempt + 1}: {e}", exc_info=True)

    logger.error(f"Failed to send media after {RetryConfig.RETRY_ATTEMPTS} attempts: {file_path}")
    TempFileManager.cleanup_file(file_path)
    return False
