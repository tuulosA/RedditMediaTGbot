# redditcommand/utils/reddit_video_resolver.py
# Robust resolver for dead external links where the reddit-hosted video still exists.

import aiohttp
import os
import re
from asyncpraw.models import Submission
from typing import Optional, Tuple, Any, Dict, List

from redditcommand.config import RedditVideoConfig
from redditcommand.utils.tempfile_utils import TempFileManager
from redditcommand.utils.session import GlobalSession
from redditcommand.utils.log_manager import LogManager

logger = LogManager.setup_main_logger()


class RedditVideoResolver:
    # ---------- Helpers to extract v.redd.it from the Submission itself ----------

    @staticmethod
    def _extract_vreddit_from_reddit_video(rv: Optional[Dict[str, Any]]) -> Optional[str]:
        """
        rv is something like post.secure_media.get("reddit_video")
        It may contain keys like fallback_url, dash_url, hls_url, scrubber_media_url.
        """
        if not isinstance(rv, dict):
            return None
        # Prefer dash_url; if not present, try fallback_url (usually a DASH_* file)
        candidates = [
            rv.get("dash_url"),
            rv.get("fallback_url"),
            rv.get("scrubber_media_url"),
            rv.get("hls_url"),
        ]
        for url in candidates:
            if not url:
                continue
            m = re.search(r"(https://v\.redd\.it/[A-Za-z0-9]+)", url)
            if m:
                return m.group(1)
        return None

    @classmethod
    def _extract_vreddit_from_submission(cls, post: Submission) -> Optional[str]:
        try:
            # 1) secure_media / media (you already have)
            sm = getattr(post, "secure_media", None)
            if isinstance(sm, dict) and "reddit_video" in sm:
                url = cls._extract_vreddit_from_reddit_video(sm.get("reddit_video"))
                if url:
                    logger.debug("[Resolver] Found v.redd.it via secure_media")
                    return url

            m = getattr(post, "media", None)
            if isinstance(m, dict) and "reddit_video" in m:
                url = cls._extract_vreddit_from_reddit_video(m.get("reddit_video"))
                if url:
                    logger.debug("[Resolver] Found v.redd.it via media")
                    return url

            # 2) **preview.reddit_video_preview** (NEW)
            pv = getattr(post, "preview", None)
            if isinstance(pv, dict) and "reddit_video_preview" in pv:
                url = cls._extract_vreddit_from_reddit_video(pv.get("reddit_video_preview"))
                if url:
                    logger.debug("[Resolver] Found v.redd.it via preview.reddit_video_preview")
                    return url

            # 3) crosspost_parent_list (you already have)
            cpl = getattr(post, "crosspost_parent_list", None)
            if isinstance(cpl, list):
                for parent in cpl:
                    if isinstance(parent, dict):
                        rv = (parent.get("secure_media") or {}).get("reddit_video") \
                            or (parent.get("media") or {}).get("reddit_video") \
                            or (parent.get("preview") or {}).get("reddit_video_preview")
                        url = cls._extract_vreddit_from_reddit_video(rv)
                        if url:
                            logger.debug("[Resolver] Found v.redd.it via crosspost_parent_list")
                            return url
        except Exception as e:
            logger.debug(f"[Resolver] Error inspecting submission media fields: {e}")
        return None

    # ---------- Network helpers ----------

    @staticmethod
    async def _get_session() -> aiohttp.ClientSession:
        return await GlobalSession.get()

    @staticmethod
    def _default_headers() -> Dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (resolver; +https://github.com/yourbot)",
            # NSFW interstitials are gated by this cookie; it’s safe to set.
            "Cookie": "over18=1",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        }

    @staticmethod
    async def fetch_post_html(url: str, session: Optional[aiohttp.ClientSession] = None) -> str:
        session = session or await RedditVideoResolver._get_session()
        async with session.get(url, headers=RedditVideoResolver._default_headers(), allow_redirects=True) as resp:
            return await resp.text()

    @staticmethod
    async def fetch_post_json(post_id: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[List[Dict[str, Any]]]:
        """
        Public JSON for a post (no auth). raw_json=1 to avoid HTML entities.
        """
        session = session or await RedditVideoResolver._get_session()
        url = f"https://www.reddit.com/comments/{post_id}.json?raw_json=1"
        try:
            async with session.get(url, headers=RedditVideoResolver._default_headers(), allow_redirects=True) as resp:
                if resp.status != 200:
                    logger.debug(f"[Resolver] JSON fetch status {resp.status} for {post_id}")
                    return None
                return await resp.json(content_type=None)
        except Exception as e:
            logger.debug(f"[Resolver] JSON fetch exception for {post_id}: {e}")
            return None

    # ---------- Extraction from HTML/JSON strings ----------

    @staticmethod
    def _extract_vreddit_from_html_like(text: str) -> Optional[str]:
        """
        Find https://v.redd.it/<id> in either plain or JSON-escaped form.
        """
        # Plain
        m = re.search(r"(https://v\.redd\.it/[A-Za-z0-9]+)", text)
        if m:
            return m.group(1)
        # JSON-escaped (https:\/\/v.redd.it\/abc123)
        m = re.search(r"https:\\/\\/v\.redd\.it\\/([A-Za-z0-9]+)", text)
        if m:
            return f"https://v.redd.it/{m.group(1)}"
        return None

    @classmethod
    def extract_vreddit_base_from_json(cls, data: List[Dict[str, Any]]) -> Optional[str]:
        """
        Walk the JSON looking for reddit_video fields or any v.redd.it URL.
        """
        try:
            # Comments JSON returns a list: [postListing, commentsListing]
            if not isinstance(data, list) or not data:
                return None

            def walk(obj: Any) -> Optional[str]:
                if isinstance(obj, dict):
                    # Direct reddit_video block
                    if "reddit_video" in obj and isinstance(obj["reddit_video"], dict):
                        url = cls._extract_vreddit_from_reddit_video(obj["reddit_video"])
                        if url:
                            return url
                    # Any string field containing v.redd.it
                    for v in obj.values():
                        found = walk(v)
                        if found:
                            return found
                elif isinstance(obj, list):
                    for item in obj:
                        found = walk(item)
                        if found:
                            return found
                elif isinstance(obj, str):
                    maybe = cls._extract_vreddit_from_html_like(obj)
                    if maybe:
                        return maybe
                return None

            return walk(data)
        except Exception as e:
            logger.debug(f"[Resolver] JSON parse error: {e}")
            return None

    # ---------- Existing DASH probing ----------

    @classmethod
    async def find_dash_url(cls, base_url: str, session: Optional[aiohttp.ClientSession] = None) -> str:
        session = session or await cls._get_session()
        for res in RedditVideoConfig.DASH_RESOLUTIONS:
            url = f"{base_url}/DASH_{res}.mp4"
            try:
                async with session.head(url, headers=cls._default_headers(), timeout=5) as resp:
                    if resp.status == 200:
                        return url
            except aiohttp.ClientError as e:
                logger.debug(f"[Resolver] DASH_{res} not accessible: {e}")
            except Exception as e:
                logger.error(f"[Resolver] Unexpected error while checking DASH_{res}: {e}", exc_info=True)
        return ""

    # ---------- Public entry points ----------

    @staticmethod
    def slugify_title(title: str) -> str:
        title = title.lower()
        title = re.sub(r"[^a-z0-9\s]", "", title)
        title = re.sub(r"\s+", "_", title)
        return title.strip("_")

    @classmethod
    def build_mobile_url(cls, subreddit: str, post_id: str, title: str) -> str:
        slug = cls.slugify_title(title or "")
        return f"https://old.reddit.com/r/{subreddit}/comments/{post_id}/{slug}/"  # use old.reddit: simpler markup

    @classmethod
    async def resolve_video(cls, post: Submission, session: Optional[aiohttp.ClientSession] = None) -> Optional[str]:
        """
        Resolve a reddit-hosted (v.redd.it) video for a Submission.
        - Finds the base v.redd.it URL via submission fields, JSON, or HTML.
        - Downloads the best DASH_* video variant.
        - If DASH_audio.mp4 exists, downloads it and muxes audio+video into a single MP4.
        - Falls back to video-only if no audio is available or mux fails.
        """
        try:
            session = session or await cls._get_session()

            # 1) Try to get v.redd.it straight from the Submission data
            base_url = cls._extract_vreddit_from_submission(post)
            if base_url:
                logger.info(f"[Resolver] Using v.redd.it from submission fields: {base_url}")

            # 2) Fall back to the public JSON API
            if not base_url:
                data = await cls.fetch_post_json(post.id, session)
                if data:
                    base_url = cls.extract_vreddit_base_from_json(data)
                    if base_url:
                        logger.info(f"[Resolver] Found v.redd.it via JSON: {base_url}")

            # 3) Fall back to HTML scraping (old.reddit for simpler DOM, with over18 cookie)
            if not base_url:
                html = await cls.fetch_post_html(
                    cls.build_mobile_url(getattr(post.subreddit, "display_name", "unknown"), post.id, post.title or ""),
                    session,
                )
                base_url = cls._extract_vreddit_from_html_like(html)
                if base_url:
                    logger.info(f"[Resolver] Found v.redd.it via HTML: {base_url}")

            if not base_url:
                logger.warning(f"[Resolver] No v.redd.it URL found for post {post.id}")
                return None

            # Locate best video track
            dash_video_url = await cls.find_dash_url(base_url, session)
            if not dash_video_url:
                logger.warning(f"[Resolver] No DASH video variant found at {base_url}")
                return None

            # Prepare temp paths
            temp_dir = TempFileManager.create_temp_dir("reddit_video_")
            base_path = os.path.join(temp_dir, f"reddit_{post.id}")
            video_path = base_path + "_v.mp4"
            audio_path = base_path + "_a.m4a"   # container/extension not critical for mux
            out_path   = base_path + ".mp4"

            # Download video
            async with session.get(dash_video_url, headers=cls._default_headers()) as resp:
                if resp.status != 200:
                    logger.warning(f"[Resolver] DASH video download failed with status {resp.status} for {dash_video_url}")
                    return None
                with open(video_path, "wb") as f:
                    f.write(await resp.read())
            logger.info(f"[Resolver] Downloaded video track to {video_path}")

            # Try to download audio (if present). If it fails, we'll return video-only.
            audio_url = f"{base_url}/DASH_audio.mp4"
            audio_downloaded = False
            try:
                async with session.get(audio_url, headers=cls._default_headers()) as aresp:
                    if aresp.status == 200:
                        with open(audio_path, "wb") as af:
                            af.write(await aresp.read())
                        audio_downloaded = True
                        logger.info(f"[Resolver] Downloaded audio track to {audio_path}")
                    else:
                        logger.info(f"[Resolver] No audio (status {aresp.status}) at {audio_url}")
            except Exception as e:
                logger.debug(f"[Resolver] Audio GET failed for {audio_url}: {e}")

            if audio_downloaded:
                # Mux audio + video using helper
                try:
                    from redditcommand.utils.media_utils import AVMuxer  # lazy import to avoid cycles at module import
                    muxed = await AVMuxer.mux_av(video_path, audio_path, out_path)
                    if muxed:
                        logger.info(f"[Resolver] Muxed A/V to {out_path}")
                        return out_path
                    logger.warning("[Resolver] A/V mux failed; falling back to video-only file.")
                except Exception as e:
                    logger.error(f"[Resolver] Exception during mux: {e}", exc_info=True)

            # Fallback: return video-only
            return video_path

        except Exception as e:
            logger.error(f"[Resolver] Error during video resolution for post {post.id}: {e}", exc_info=True)

        return None
