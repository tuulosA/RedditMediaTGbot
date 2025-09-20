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
        # Try common DASH renditions in order, using the shared session
        dash_urls = [f"{media_url.rstrip('/')}/DASH_{res}.mp4" for res in RedditVideoConfig.DASH_RESOLUTIONS]

        valid_url = await MediaDownloader.find_first_valid_url(dash_urls, session=self.session)
        if not valid_url:
            logger.info(f"No valid DASH URL for {media_url}")
            return None

        post_id = (post.id if post else TempFileManager.extract_post_id_from_url(media_url)) or "unknown"
        temp_dir = TempFileManager.create_temp_dir("reddit_video_")
        file_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")

        return await MediaDownloader.download_file(valid_url, file_path, session=self.session)

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
            # Extract shortcode defensively
            base = media_url.split("?")[0].rstrip("/")
            parts = [p for p in base.split("/") if p]
            shortcode = parts[-1] if parts else ""
            if not shortcode or any(c in shortcode for c in "/?#&"):
                logger.warning(f"Invalid Streamable shortcode from URL: {media_url}")
                return None

            api_url = f"https://api.streamable.com/videos/{shortcode}"
            async with self.session.get(api_url) as resp:
                if resp.status != 200:
                    logger.info(f"Streamable API returned {resp.status} for {shortcode}")
                    return None
                data = await resp.json()

            # Prefer mp4, then progressive variants if present
            files = data.get("files", {}) or {}
            path = None
            if "mp4" in files and isinstance(files["mp4"], dict):
                path = files["mp4"].get("url")
            if not path and "mp4-mobile" in files and isinstance(files["mp4-mobile"], dict):
                path = files["mp4-mobile"].get("url")

            if not path:
                logger.info(f"No downloadable file in Streamable response for {shortcode}")
                return None

            resolved = f"https:{path}" if path and not path.startswith("http") else path
            if not resolved:
                return None

            post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url) or shortcode or "unknown"
            temp_dir = TempFileManager.create_temp_dir("reddit_streamable_")
            file_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")

            return await MediaDownloader.download_file(resolved, file_path, session=self.session)
        except Exception as e:
            logger.error(f"Streamable error: {e}", exc_info=True)
        return None

    async def _redgifs(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        try:
            # Extract gif id defensively, RedGifs URLs are often .../watch/<id>
            base = media_url.split("?")[0].rstrip("/")
            parts = [p for p in base.split("/") if p]
            gif_id = parts[-1] if parts else ""
            if gif_id.lower() == "watch" and len(parts) >= 2:
                gif_id = parts[-2]
            if not gif_id or any(c in gif_id for c in "/?#&"):
                logger.warning(f"Invalid RedGifs id from URL: {media_url}")
                return None

            api = RedGifsAPI()
            await api.login()
            try:
                gif = await api.get_gif(gif_id)
            finally:
                await api.close()

            url = getattr(gif.urls, "hd", None) or getattr(gif.urls, "sd", None) or getattr(gif.urls, "file_url", None)
            if not url:
                logger.info(f"RedGifs returned no downloadable URL for id {gif_id}")
                return None

            post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url) or gif_id or "unknown"
            temp_dir = TempFileManager.create_temp_dir("reddit_redgifs_")
            file_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")

            return await MediaDownloader.download_file(url, file_path, session=self.session)
        except Exception as e:
            logger.error(f"RedGifs error: {e}", exc_info=True)
        return None

    async def _yt_dlp(self, media_url: str, post: Optional[Submission]) -> Optional[str]:
        post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url) or "unknown"
        return await self._download_with_ytdlp(media_url, post_id)

    async def _download_with_ytdlp(self, url: str, post_id: str) -> Optional[str]:
        """
        Download a video with yt-dlp to a temp directory using an output template.
        Forces an mp4 merge/remux and handles timeouts. Returns the final file path
        or None on failure.
        """
        temp_dir = TempFileManager.create_temp_dir("ytdlp_video_")
        output_tpl = os.path.join(temp_dir, f"reddit_{post_id}.%(ext)s")

        command = [
            "yt-dlp",
            "--quiet",
            "--no-warnings",
            "--no-part",
            "--no-mtime",
            "--no-playlist",
            "--no-check-certificate",
            "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
            "--merge-output-format", "mp4",
            "--output", output_tpl,
            url,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                _, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=getattr(RedditVideoConfig, "YTDLP_TIMEOUT", 600),
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                logger.error("yt-dlp timed out")
                TempFileManager.cleanup_file(temp_dir)
                return None

            if process.returncode != 0:
                err = (stderr.decode(errors="ignore") or "").strip()
                logger.error(f"yt-dlp failed: {err}")
                TempFileManager.cleanup_file(temp_dir)
                return None

            # Resolve the resulting file. We prefer mp4, but check a couple of common fallbacks.
            candidates = [
                os.path.join(temp_dir, f"reddit_{post_id}.mp4"),
                os.path.join(temp_dir, f"reddit_{post_id}.m4v"),
            ]
            for cand in candidates:
                if os.path.exists(cand):
                    return cand

            # As a last resort, find any file that matches the template prefix.
            prefix = f"reddit_{post_id}."
            for name in os.listdir(temp_dir):
                if name.startswith(prefix):
                    path = os.path.join(temp_dir, name)
                    if os.path.isfile(path):
                        return path

            logger.error("yt-dlp succeeded but no output file was found")
        except Exception as e:
            logger.error(f"yt-dlp exception: {e}", exc_info=True)

        TempFileManager.cleanup_file(temp_dir)
        return None
