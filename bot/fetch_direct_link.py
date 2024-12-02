import os
import aiohttp
import logging
import asyncio
import subprocess
from typing import Optional, Tuple
from bot.utils.tempfile_utils import create_temp_dir
from bot.utils.blacklist_manager import add_to_blacklist

logger = logging.getLogger(__name__)


async def fetch_direct_link(media_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Resolves a direct media link from a given URL.
    """

    try:
        if "v.redd.it" in media_url:
            return await process_v_reddit(media_url, session)
        if "imgur.com" in media_url:
            return await process_imgur(media_url)
        if media_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.mp4')):
            return media_url

        logger.warning(f"Unsupported URL format: {media_url}")
    except Exception as e:
        logger.error(f"Error fetching direct link for {media_url}: {e}", exc_info=True)
    return None


async def process_v_reddit(media_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Processes v.redd.it media by resolving valid DASH URLs and downloading the video.
    """
    resolutions = ['1080', '720', '480', '360']
    dash_urls = [f"{media_url}/DASH_{res}.mp4" for res in resolutions]

    valid_url = await find_valid_dash_url(dash_urls, session)
    if not valid_url:
        logger.error(f"No valid DASH URLs found for {media_url}")
        return None

    temp_dir = create_temp_dir("reddit_video_")
    temp_file_path = os.path.join(temp_dir, "video.mp4")
    return await download_file(valid_url, temp_file_path, session)


async def process_imgur(media_url: str) -> Optional[str]:
    """
    Resolves direct links for Imgur media, including downloading and converting .gifv files.
    """
    try:
        file_path, _ = await yt_dlp_download(media_url)
        if not file_path:
            logger.error(f"Failed to download Imgur media: {media_url}")
            return None

        if file_path.endswith(".gifv"):
            mp4_path = file_path.replace(".gifv", ".mp4")
            if convert_to_mp4(file_path, mp4_path):
                return mp4_path
            logger.error(f"Failed to convert .gifv to .mp4: {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Error processing Imgur media {media_url}: {e}", exc_info=True)
    return None


async def find_valid_dash_url(dash_urls: list[str], session: aiohttp.ClientSession) -> Optional[str]:
    """
    Checks DASH URLs for availability and returns the first valid URL.
    """
    for url in dash_urls:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    logger.info(f"Valid DASH URL: {url}")
                    return url
        except aiohttp.ClientError:
            logger.debug(f"Failed to validate DASH URL: {url}")
    return None


async def download_file(url: str, file_path: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Downloads a file from a URL to the specified path.
    """
    try:
        async with session.get(url, timeout=20) as response:
            if response.status == 200:
                with open(file_path, 'wb') as file:
                    file.write(await response.read())
                logger.info(f"Downloaded media to: {file_path}")
                return file_path
    except Exception as e:
        logger.error(f"Error downloading file from {url}: {e}", exc_info=True)
    return None


def convert_to_mp4(input_file: str, output_file: str) -> bool:
    """
    Converts .gifv files to .mp4 using FFmpeg.
    """
    command = [
        "ffmpeg", "-y",
        "-i", input_file,
        "-movflags", "faststart",
        "-pix_fmt", "yuv420p",
        output_file
    ]
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"Converted {input_file} to MP4: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg conversion failed: {e}", exc_info=True)
    return False


async def yt_dlp_download(media_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Downloads media using yt-dlp and returns the file path and temp directory.
    """
    temp_dir = create_temp_dir("imgur_video_")
    outtmpl = os.path.join(temp_dir, '%(title)s.%(ext)s')

    command = [
        "yt-dlp",
        "--quiet",
        "--no-warnings",
        "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4",
        "--output", outtmpl,
        media_url
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"yt-dlp failed: {stderr.decode().strip()}")
            if "404" in stderr.decode():
                add_to_blacklist(media_url)
            return None, temp_dir

        for file_name in os.listdir(temp_dir):
            if file_name.endswith(('.mp4', '.m4a')):
                return os.path.join(temp_dir, file_name), temp_dir

        logger.error("yt-dlp completed but no valid file found.")
    except Exception as e:
        logger.error(f"yt-dlp download error: {e}", exc_info=True)
        add_to_blacklist(media_url)
    return None, temp_dir
