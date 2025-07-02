# Updated media_handler.py to use Compressor class for size validation

import asyncio
import logging
import aiohttp
import os
import urllib.parse

from typing import Optional
from telegram import Update
from telegram.error import TimedOut
from asyncpraw import Reddit
from asyncpraw.models import Submission

from .config import MediaConfig, RetryConfig
from .handle_direct_link import MediaLinkResolver

from redditcommand.utils.media_utils import MediaSender, MediaUtils, MediaDownloader
from redditcommand.utils.compressor import Compressor
from redditcommand.utils.tempfile_utils import TempFileManager

logger = logging.getLogger(__name__)


class MediaProcessor:
    def __init__(self, reddit: Reddit, update: Update):
        self.reddit = reddit
        self.update = update
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def process_batch(
        self,
        media_list: list[Submission],
        include_comments: bool,
        include_flair: bool,
        include_title: bool
    ) -> list[Submission]:
        tasks = [
            self.process_single(media, include_comments, include_flair, include_title)
            for media in media_list
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [result for result in results if isinstance(result, Submission)]

    async def process_single(
        self,
        media: Submission,
        include_comments: bool = False,
        include_flair: bool = False,
        include_title: bool = False,
    ) -> Optional[Submission]:
        if not media.url:
            logger.warning("Media URL is missing or invalid.")
            return None

        try:
            caption = await self.build_caption(media, include_comments, include_flair, include_title)

            resolved_url = await self.resolve_media_url(media)
            if not resolved_url:
                return None

            file_path = await self.download_and_validate_media(resolved_url, media.id)
            if not file_path:
                return None

            if await self.upload_media(file_path, self.update, caption):
                return media

        except Exception as e:
            logger.error(f"Error processing media {media.url}: {e}", exc_info=True)

        return None

    async def build_caption(
        self,
        media: Submission,
        include_comments: bool,
        include_flair: bool,
        include_title: bool
    ) -> Optional[str]:
        parts = []
        if include_title and media.title:
            parts.append(media.title.strip())
        if include_flair and media.link_flair_text:
            parts.append(f"[{media.link_flair_text.strip()}]")
        if include_comments:
            top_comment = await MediaUtils.fetch_top_comment(media)
            if top_comment:
                parts.append(f"💬 {top_comment.strip()}")

        caption = "\n".join(parts)
        if len(caption) > 1024:
            logger.warning(f"Caption too long ({len(caption)}), truncating.")
            caption = caption[:1021] + "…"
        return caption or None

    async def resolve_media_url(self, post: Submission) -> Optional[str]:
        try:
            media_url = post.url
            if media_url.startswith("/tmp") and await MediaUtils.validate_file(media_url):
                return media_url
            if "gallery" in media_url:
                return await MediaUtils.resolve_reddit_gallery(media_url.split("/")[-1], self.reddit)
            
            resolver = MediaLinkResolver(self.session)
            return await resolver.resolve(media_url, post=post)

        except Exception as e:
            logger.error(f"Error resolving media URL for post {post.id}: {e}", exc_info=True)
            return None

    async def download_and_validate_media(
        self,
        resolved_url: str,
        post_id: Optional[str] = None
    ) -> Optional[str]:
        file_path = await self.download_file(resolved_url, post_id)
        if not file_path:
            return None

        if await Compressor.is_valid(file_path, MediaConfig.MAX_FILE_SIZE_MB):
            return file_path

        logger.warning(f"File too large after download: {file_path}")
        TempFileManager.cleanup_file(file_path)
        return None

    async def download_file(self, resolved_url: str, post_id: Optional[str]) -> Optional[str]:
        if os.path.isfile(resolved_url):
            if await MediaUtils.validate_file(resolved_url):
                return resolved_url
            return None

        if not resolved_url.startswith(("http://", "https://")):
            return resolved_url if await MediaUtils.validate_file(resolved_url) else None

        temp_dir = TempFileManager.create_temp_dir("reddit_media_")
        path = urllib.parse.urlparse(resolved_url).path
        ext = os.path.splitext(path)[1] or ".mp4"
        final_id = post_id or TempFileManager.extract_post_id_from_url(resolved_url) or "unknown"
        file_path = os.path.join(temp_dir, f"reddit_{final_id}{ext}")

        file_path = await MediaDownloader.download_file(resolved_url, file_path, self.session)
        if file_path and file_path.endswith(".gif"):
            converted = await MediaUtils.convert_gif_to_mp4(file_path)
            TempFileManager.cleanup_file(file_path)
            return converted

        return file_path

    async def upload_media(self, file_path: str, target, caption: Optional[str]) -> bool:
        handler = MediaSender.determine_type(file_path)
        if not handler:
            logger.warning(f"Unsupported media type: {file_path}")
            return False

        for attempt in range(RetryConfig.RETRY_ATTEMPTS):
            try:
                await handler(file_path, target, caption=caption)
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
