# redditcommand/utils/reddit_video_resolver.py
# this is primarily a hacky method for dealing with dead imgur links, as the media file is often still available from reddit's server

import logging
import aiohttp
import os
import re
from asyncpraw.models import Submission
from typing import Optional

from redditcommand.utils.tempfile_utils import TempFileManager

logger = logging.getLogger(__name__)


class RedditVideoResolver:
    RESOLUTIONS = ["1080", "720", "480", "360"]

    @staticmethod
    def slugify_title(title: str) -> str:
        title = title.lower()
        title = re.sub(r"[^a-z0-9\s]", "", title)
        title = re.sub(r"\s+", "_", title)
        return title.strip("_")

    @classmethod
    def build_mobile_url(cls, subreddit: str, post_id: str, title: str) -> str:
        slug = cls.slugify_title(title)
        return f"https://m.reddit.com/r/{subreddit}/comments/{post_id}/{slug}/"

    @staticmethod
    async def fetch_post_html(url: str, session: aiohttp.ClientSession) -> str:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with session.get(url, headers=headers, allow_redirects=True) as resp:
            return await resp.text()

    @staticmethod
    def extract_vreddit_base(html: str) -> str:
        match = re.search(r'https://v\.redd\.it/[a-zA-Z0-9]+', html)
        return match.group(0) if match else ""

    @classmethod
    async def find_dash_url(cls, base_url: str, session: aiohttp.ClientSession) -> str:
        for res in cls.RESOLUTIONS:
            url = f"{base_url}/DASH_{res}.mp4"
            try:
                async with session.head(url, timeout=5) as resp:
                    if resp.status == 200:
                        return url
            except aiohttp.ClientError as e:
                logger.debug(f"[Resolver] DASH_{res} not accessible: {e}")
            except Exception as e:
                logger.error(f"[Resolver] Unexpected error while checking DASH_{res}: {e}", exc_info=True)
        return ""

    @classmethod
    async def resolve_video(cls, post: Submission, session: aiohttp.ClientSession) -> Optional[str]:
        try:
            html = await cls.fetch_post_html(
                cls.build_mobile_url(post.subreddit.display_name, post.id, post.title), session
            )
            base_url = cls.extract_vreddit_base(html)
            if not base_url:
                logger.warning(f"[Resolver] No v.redd.it URL found in HTML for post {post.id}")
                return None

            dash_url = await cls.find_dash_url(base_url, session)
            if not dash_url:
                logger.warning(f"[Resolver] No DASH variant found at {base_url}")
                return None

            temp_dir = TempFileManager.create_temp_dir("reddit_video_")
            file_path = os.path.join(temp_dir, f"reddit_{post.id}.mp4")

            async with session.get(dash_url) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        f.write(await resp.read())
                    logger.info(f"[Resolver] Successfully downloaded video to {file_path}")
                    return file_path
                else:
                    logger.warning(f"[Resolver] DASH file download failed with status {resp.status} for {dash_url}")

        except Exception as e:
            logger.error(f"[Resolver] Error during video resolution for post {post.id}: {e}", exc_info=True)

        return None
