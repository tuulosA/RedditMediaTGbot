# redditcommand/handle_direct_link.py

import os
import aiohttp
import asyncio

from typing import Optional
from redgifs.aio import API as RedGifsAPI
from asyncpraw.models import Submission

from redditcommand.config import RedditVideoConfig

from redditcommand.utils.log_manager import LogManager
from redditcommand.utils.tempfile_utils import TempFileManager
from redditcommand.utils.media_utils import MediaDownloader
from redditcommand.utils.reddit_video_resolver import RedditVideoResolver
from redditcommand.utils.session import GlobalSession

logger = LogManager.setup_main_logger()


class MediaLinkResolver:
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None

    async def init(self):
        self.session = await GlobalSession.get()

    async def resolve(self, media_url: str, post: Optional[Submission] = None) -> Optional[str]:
        if self.session is None:
            await self.init()

        try:
            if "v.redd.it" in media_url:
                return await self._v_reddit(media_url, post)
            if "imgur.com" in media_url:
                return await self._imgur(media_url, post)
            if "streamable.com" in media_url:
                return await self._streamable(media_url, post)
            if "redgifs.com" in media_url:
                return await self._redgifs(media_url, post)
            if any(domain in media_url for domain in ["kick.com", "twitch.tv", "youtube.com", "youtu.be", "x.com", "twitter.com"]):
                return await self._yt_dlp(media_url, post)
            if media_url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".mp4")):
                return media_url

            logger.warning(f"Unsupported URL format: {media_url}")
        except Exception as e:
            logger.error(f"Error resolving direct link for {media_url}: {e}", exc_info=True)
        return None
    
    async def _v_reddit(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        dash_urls = [f"{media_url}/DASH_{res}.mp4" for res in RedditVideoConfig.DASH_RESOLUTIONS]

        valid_url = await MediaDownloader.find_first_valid_url(dash_urls)
        if not valid_url:
            return None

        post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url)
        file_path = os.path.join(
            TempFileManager.create_temp_dir("reddit_video_"),
            f"reddit_{post_id or 'unknown'}.mp4"
        )

        return await MediaDownloader.download_file(valid_url, file_path)

    async def _imgur(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        try:
            if post:
                fallback = await RedditVideoResolver.resolve_video(post)
                if fallback:
                    return fallback
            logger.warning(f"RedditVideoResolver failed and yt-dlp is disabled for {media_url}")
        except Exception as e:
            logger.error(f"Error processing Imgur: {e}", exc_info=True)
        return None

    async def _streamable(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        try:
            shortcode = media_url.rstrip("/").split("/")[-1].split("?")[0]
            api_url = f"https://api.streamable.com/videos/{shortcode}"
            async with self.session.get(api_url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                path = data.get("files", {}).get("mp4", {}).get("url")
                if not path:
                    return None
                resolved = f"https:{path}" if not path.startswith("http") else path
                post_id = post.id if post else "unknown"
                file_path = os.path.join(
                    TempFileManager.create_temp_dir("reddit_streamable_"),
                    f"reddit_{post_id}.mp4"
                )
                return await MediaDownloader.download_file(resolved, file_path)  # ⬅️ session removed
        except Exception as e:
            logger.error(f"Streamable error: {e}", exc_info=True)
        return None

    async def _redgifs(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        try:
            gif_id = media_url.rstrip("/").split("/")[-1]
            api = RedGifsAPI()
            await api.login()
            gif = await api.get_gif(gif_id)
            await api.close()
            url = gif.urls.hd or gif.urls.sd or gif.urls.file_url
            if not url:
                return None
            post_id = post.id if post else "unknown"
            file_path = os.path.join(
                TempFileManager.create_temp_dir("reddit_redgifs_"),
                f"reddit_{post_id}.mp4"
            )
            return await MediaDownloader.download_file(url, file_path)  # ⬅️ session removed
        except Exception as e:
            logger.error(f"RedGifs error: {e}", exc_info=True)
        return None

    async def _yt_dlp(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url) or "unknown"
        return await self._download_with_ytdlp(media_url, post_id)

    async def _download_with_ytdlp(self, url: str, post_id: str) -> Optional[str]:
        temp_dir = TempFileManager.create_temp_dir("ytdlp_video_")
        output_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")
        command = [
            "yt-dlp", "--quiet", "--no-warnings", "--no-part", "--no-mtime",
            "--no-playlist", "--no-check-certificate",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--output", output_path,
            url,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()

            if process.returncode == 0 and os.path.exists(output_path):
                return output_path

            logger.error(f"yt-dlp failed: {stderr.decode().strip()}")
        except Exception as e:
            logger.error(f"yt-dlp exception: {e}", exc_info=True)

        TempFileManager.cleanup_file(temp_dir)
        return None
