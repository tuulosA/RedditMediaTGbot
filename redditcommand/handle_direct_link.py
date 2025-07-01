# handle_direct_link.py

import os
import aiohttp
import logging
import asyncio

from typing import Optional, Tuple
from redgifs.aio import API as RedGifsAPI
from asyncpraw.models import Submission

from redditcommand.utils.tempfile_utils import TempFileManager
from redditcommand.utils.media_utils import MediaUtils, MediaDownloader
from redditcommand.utils.reddit_video_resolver import RedditVideoResolver

logger = logging.getLogger(__name__)


async def handle_direct_link(
    media_url: str,
    session: aiohttp.ClientSession,
    post: Optional[Submission] = None
) -> Optional[str]:
    try:
        if "v.redd.it" in media_url:
            return await process_v_reddit(media_url, session, post)

        if "imgur.com" in media_url:
            return await process_imgur(media_url, post, session)

        if "streamable.com" in media_url:
            return await process_streamable(media_url, session, post)

        if "redgifs.com" in media_url:
            return await process_redgifs(media_url, session, post)

        if "kick.com" in media_url:
            return await process_kick(media_url, session, post)

        if "twitch.tv" in media_url:
            return await process_twitch(media_url, session, post)

        if "youtube.com" in media_url or "youtu.be" in media_url:
            return await process_youtube(media_url, session, post)

        if "x.com" in media_url or "twitter.com" in media_url:
            return await process_twitter(media_url, session, post)

        if media_url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".mp4")):
            return media_url

        logger.warning(f"Unsupported URL format: {media_url}")

    except Exception as e:
        logger.error(f"Error resolving direct link for {media_url}: {e}", exc_info=True)

    return None


async def process_v_reddit(
    media_url: str,
    session: aiohttp.ClientSession,
    post: Optional[Submission] = None
) -> Optional[str]:
    dash_urls = [f"{media_url}/DASH_{res}.mp4" for res in ["1080", "720", "480", "360"]]
    valid_url = await MediaDownloader.find_first_valid_url(dash_urls, session)

    if not valid_url:
        logger.error(f"No valid DASH URL found for {media_url}")
        return None

    post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url) or "unknown"
    temp_dir = TempFileManager.create_temp_dir("reddit_video_")
    file_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")

    return await MediaDownloader.download_file(valid_url, file_path, session)


async def process_imgur(
    media_url: str,
    post: Optional[Submission],
    session: aiohttp.ClientSession
) -> Optional[str]:
    try:
        if post:
            logger.info(f"Trying RedditVideoResolver for Imgur URL using Reddit post metadata: {media_url}")
            fallback_path = await RedditVideoResolver.resolve_video(post, session)
            if fallback_path:
                logger.info(f"RedditVideoResolver succeeded for {media_url}")
                return fallback_path
            else:
                logger.warning(f"RedditVideoResolver failed for {media_url}")

        # yt-dlp functionality is disabled
        # logger.info(f"Attempting yt-dlp for {media_url}")
        # file_path, _ = await download_with_ytdlp(media_url)
        # if file_path:
        #     logger.info(f"yt-dlp succeeded for {media_url}")
        #     if file_path.endswith(".gifv"):
        #         mp4_path = file_path.replace(".gifv", ".mp4")
        #         converted = await MediaUtils.convert_gifv(file_path, mp4_path)
        #         if converted:
        #             return converted
        #         logger.warning(f"FFmpeg conversion failed for {file_path}, using original")
        #     return file_path

        logger.warning(f"RedditVideoResolver failed and yt-dlp is disabled for {media_url}")
        return None

    except Exception as e:
        logger.error(f"Error processing Imgur media: {media_url}: {e}", exc_info=True)
        return None


async def process_streamable(
    media_url: str,
    session: aiohttp.ClientSession,
    post: Optional[Submission] = None
) -> Optional[str]:
    try:
        shortcode = media_url.rstrip("/").split("/")[-1].split("?")[0]
        api_url = f"https://api.streamable.com/videos/{shortcode}"

        async with session.get(api_url) as resp:
            if resp.status != 200:
                logger.warning(f"Streamable API returned {resp.status} for {media_url}")
                return None

            data = await resp.json()
            files = data.get("files", {})
            mp4_path = files.get("mp4", {}).get("url")

            if not mp4_path:
                logger.warning(f"No valid MP4 found in API response for: {media_url}")
                return None

            resolved_url = mp4_path.strip()
            if not resolved_url.startswith("http"):
                resolved_url = f"https:{resolved_url}"

            logger.info(f"Resolved Streamable URL: {media_url} -> {resolved_url}")

            post_id = post.id if post else "unknown"
            temp_dir = TempFileManager.create_temp_dir("reddit_streamable_")
            file_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")

            return await MediaDownloader.download_file(resolved_url, file_path, session)

    except Exception as e:
        logger.error(f"Error processing Streamable link {media_url}: {e}", exc_info=True)
        return None


async def process_redgifs(
    media_url: str,
    session: aiohttp.ClientSession,
    post: Optional[Submission] = None
) -> Optional[str]:
    try:
        gif_id = media_url.rstrip("/").split("/")[-1]
        api = RedGifsAPI()
        await api.login()
        gif = await api.get_gif(gif_id)
        await api.close()

        resolved_url = gif.urls.hd or gif.urls.sd or gif.urls.file_url
        if not resolved_url:
            logger.warning(f"No downloadable URL found for RedGifs ID: {gif_id}")
            return None

        post_id = post.id if post else "unknown"
        temp_dir = TempFileManager.create_temp_dir("reddit_redgifs_")
        file_path = os.path.join(temp_dir, f"reddit_{post_id}.mp4")

        return await MediaDownloader.download_file(resolved_url, file_path, session)

    except Exception as e:
        logger.error(f"Error processing RedGifs link {media_url}: {e}", exc_info=True)
        return None

    
async def process_kick(media_url: str, session: aiohttp.ClientSession, post: Optional[Submission]) -> Optional[str]:
    logger.info(f"Processing Kick clip: {media_url}")
    return await process_with_ytdlp(media_url, post)

async def process_twitch(media_url: str, session: aiohttp.ClientSession, post: Optional[Submission]) -> Optional[str]:
    logger.info(f"Processing Twitch clip: {media_url}")
    return await process_with_ytdlp(media_url, post)

async def process_youtube(media_url: str, session: aiohttp.ClientSession, post: Optional[Submission]) -> Optional[str]:
    logger.info(f"Processing YouTube clip: {media_url}")
    return await process_with_ytdlp(media_url, post)

async def process_twitter(media_url: str, session: aiohttp.ClientSession, post: Optional[Submission]) -> Optional[str]:
    logger.info(f"Processing Twitter/X post: {media_url}")
    return await process_with_ytdlp(media_url, post)

async def process_with_ytdlp(media_url: str, post: Optional[Submission]) -> Optional[str]:
    post_id = post.id if post else TempFileManager.extract_post_id_from_url(media_url) or "unknown"
    file_path, _ = await download_with_ytdlp(media_url, post_id)
    return file_path

async def download_with_ytdlp(media_url: str, post_id: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
    temp_dir = TempFileManager.create_temp_dir("ytdlp_video_")
    safe_name = f"reddit_{post_id or 'unknown'}"
    output_path = os.path.join(temp_dir, f"{safe_name}.mp4")

    command = [
        "yt-dlp", "--quiet", "--no-warnings", "--no-part", "--no-mtime",
        "--no-playlist", "--no-check-certificate",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "--output", output_path,
        media_url,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            err_msg = stderr.decode().strip()
            logger.error(f"yt-dlp failed: {err_msg}")
            return None, temp_dir

        if os.path.exists(output_path):
            return output_path, temp_dir

        logger.error("yt-dlp finished but no media file found")
    except Exception as e:
        logger.error(f"yt-dlp error: {e}", exc_info=True)

    TempFileManager.cleanup_file(temp_dir)
    return None, temp_dir
