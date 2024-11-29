import os
import aiohttp
import logging
from reddit.utils.tempfile_utils import create_temp_dir
import asyncio
from typing import Optional, Tuple
import subprocess
from reddit.utils.blacklist_manager import add_to_blacklist, is_blacklisted

logger = logging.getLogger(__name__)


async def fetch_direct_link(media_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Resolves a direct media link from a given URL.
    """
    logger.info(f"Fetching direct link for media URL: {media_url}")

    if is_blacklisted(media_url):
        logger.warning(f"Media URL is blacklisted: {media_url}")
        return None

    try:
        if 'v.redd.it' in media_url:
            return await process_v_reddit(media_url, session)
        elif 'imgur.com' in media_url:
            return await process_imgur(media_url)
        elif media_url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.mp4')):
            return media_url
        else:
            logger.warning(f"Unsupported media URL format: {media_url}")
            return None
    except Exception as e:
        logger.error(f"Error fetching direct link for URL {media_url}: {e}", exc_info=True)
        return None


async def process_v_reddit(media_url: str, session: aiohttp.ClientSession) -> Optional[str]:
    """
    Processes v.redd.it media by resolving valid DASH URLs and downloading the video.
    """
    logger.info(f"Processing v.redd.it media: {media_url}")
    resolutions = ['1080', '720', '480', '360']
    dash_urls = [f"{media_url}/DASH_{res}.mp4" for res in resolutions]

    async def check_dash_url(dash_url: str) -> Optional[str]:
        try:
            async with session.get(dash_url, timeout=10) as response:
                if response.status == 200:
                    logger.info(f"Valid DASH URL found: {dash_url}")
                    return dash_url
        except aiohttp.ClientError as e:
            logger.warning(f"Error checking DASH URL {dash_url}: {e}")
        return None

    temp_dir = None
    try:
        results = await asyncio.gather(*(check_dash_url(url) for url in dash_urls))
        valid_url = next((url for url in results if url), None)

        if valid_url:
            logger.info(f"Selected DASH URL: {valid_url}")
            temp_dir = create_temp_dir("reddit_video_")
            temp_file_path = os.path.join(temp_dir, "video.mp4")

            async with session.get(valid_url) as response:
                if response.status == 200:
                    with open(temp_file_path, 'wb') as temp_file:
                        temp_file.write(await response.read())
                    logger.info(f"Media saved to: {temp_file_path}")
                    return temp_file_path
                else:
                    logger.error(f"Failed to download media: {valid_url}, HTTP {response.status}")
                    return None
        else:
            logger.error(f"No valid DASH URLs found for v.redd.it media: {media_url}")
            return None
    except Exception as e:
        logger.error(f"Error processing v.redd.it media {media_url}: {e}", exc_info=True)
        return None
    finally:
        if temp_dir and not os.listdir(temp_dir):
            os.rmdir(temp_dir)


async def process_imgur(media_url: str) -> Optional[str]:
    """
    Resolves direct links for Imgur media, including downloading and converting .gifv files.
    """
    logger.info(f"Processing Imgur media: {media_url}")
    try:
        result = await yt_dlp_download(media_url)
        if not result:
            logger.error(f"Failed to download Imgur media: {media_url}")
            return None

        file_path, _ = result
        if file_path and file_path.endswith('.gifv'):
            mp4_path = file_path.replace('.gifv', '.mp4')
            if convert_to_mp4(file_path, mp4_path):
                logger.info(f"Converted .gifv to .mp4: {mp4_path}")
                return mp4_path
            else:
                logger.error(f"Failed to convert .gifv to .mp4: {file_path}")
                return None
        elif file_path:  # For non-gifv files
            return file_path
        else:
            logger.error(f"File path is invalid or None for Imgur media: {media_url}")
            return None
    except Exception as e:
        logger.error(f"Error processing Imgur media {media_url}: {e}", exc_info=True)
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
        logger.debug(f"Running FFmpeg command: {' '.join(command)}")
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"Successfully converted {input_file} to MP4: {output_file}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error during FFmpeg conversion: {e}", exc_info=True)
        return False


async def yt_dlp_download(media_url: str) -> Tuple[Optional[str], Optional[str]]:
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
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_message = stderr.decode().strip()
            logger.error(f"yt-dlp failed with code {process.returncode}: {error_message}")
            if "404" in error_message:
                logger.warning(f"URL not found (404): {media_url}. Adding to blacklist.")
                add_to_blacklist(media_url)
            return None, temp_dir

        logger.debug(f"yt-dlp output: {stdout.decode().strip()}")
        for file_name in os.listdir(temp_dir):
            if file_name.endswith(('.mp4', '.m4a')):
                file_path = os.path.join(temp_dir, file_name)
                logger.info(f"Media downloaded to: {file_path}")
                return file_path, temp_dir

        logger.error("yt-dlp completed but no valid file found.")
        return None, temp_dir
    except Exception as e:
        logger.error(f"Unexpected error during yt-dlp download: {e}", exc_info=True)
        add_to_blacklist(media_url)
        return None, temp_dir
