# redditcommand/utils/compressor.py

import os
import asyncio

from redditcommand.utils.tempfile_utils import TempFileManager
from redditcommand.utils.log_manager import LogManager

logger = LogManager.setup_main_logger()


class Compressor:
    @staticmethod
    async def validate_and_compress(file_path: str, max_size_mb: int) -> bool:
        if not os.path.exists(file_path):
            logger.warning(f"Validation failed: File does not exist: {file_path}")
            return False

        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        if size_mb > 100:
            logger.warning(f"Skipping file: too large to process ({size_mb:.2f} MB > 100 MB): {file_path}")
            return False

        if size_mb <= max_size_mb:
            logger.debug(f"File size is valid: {size_mb:.2f} MB <= {max_size_mb} MB")
            return True

        logger.warning(f"File size exceeds limit: {size_mb:.2f} MB > {max_size_mb} MB")
        output_path = file_path.replace(".mp4", "_compressed.mp4")

        if await Compressor.compress(file_path, output_path, max_size_mb):
            os.replace(output_path, file_path)
            return True

        return False

    @staticmethod
    async def compress(input_path: str, output_path: str, target_size_mb: int = 50, max_attempts: int = 3) -> bool:
        crf = 32
        max_bitrate = 2000

        for attempt in range(max_attempts):
            try:
                logger.info(f"Compression attempt {attempt + 1} for {input_path} with CRF={crf}, Max Bitrate={max_bitrate}")
                cmd = [
                    "ffmpeg", "-y", "-i", input_path,
                    "-vcodec", "libx264", "-crf", str(crf), "-preset", "ultrafast",
                    "-vf", "scale=1280:-2", "-acodec", "aac", "-b:a", "96k",
                    output_path
                ]
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await proc.communicate()

                if proc.returncode != 0:
                    logger.error(f"Compression failed: {stderr.decode()}")
                    TempFileManager.cleanup_file(output_path)
                    continue

                new_size = os.path.getsize(output_path) / (1024 * 1024)
                if new_size <= target_size_mb:
                    logger.info(f"Compression successful: {new_size:.2f} MB <= {target_size_mb} MB")
                    TempFileManager.cleanup_file(input_path)
                    return True
                else:
                    logger.warning(f"Still too large: {new_size:.2f} MB > {target_size_mb} MB")
                    TempFileManager.cleanup_file(output_path)

            except Exception as e:
                logger.error(f"Compression error (attempt {attempt + 1}): {e}", exc_info=True)

            crf += 2
            max_bitrate -= 500

        logger.error(f"Failed to compress {input_path} below {target_size_mb} MB after {max_attempts} attempts.")
        return False