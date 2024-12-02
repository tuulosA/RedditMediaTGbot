import os
import logging
import subprocess
from bot.utils.media_utils import cleanup_file

logger = logging.getLogger(__name__)


def is_file_size_valid(file_path: str, max_size_mb: int) -> bool:
    """
    Checks if a file's size is within the specified maximum size in MB.
    If the file size exceeds the limit, attempts to compress it.
    """
    if not os.path.exists(file_path):
        logger.warning(f"Validation failed: File does not exist: {file_path}")
        return False

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        logger.debug(f"File size is valid: {file_size_mb:.2f} MB <= {max_size_mb} MB")
        return True

    logger.warning(f"File size exceeds limit: {file_size_mb:.2f} MB > {max_size_mb} MB")
    output_path = file_path.replace(".mp4", "_compressed.mp4")

    if compress_video(file_path, output_path, max_size_mb):
        os.replace(output_path, file_path)  # Replace the original file with the compressed one
        return True

    return False


def compress_video(input_path: str, output_path: str, target_size_mb: int = 50, max_attempts: int = 3) -> bool:
    """
    Compresses a video to ensure it is below the specified size limit.
    """
    crf = 32  # Starting compression factor
    max_bitrate = 2000  # Starting bitrate (in kbps)

    for attempt in range(max_attempts):
        try:
            logger.info(f"Compression attempt {attempt + 1} for {input_path} with CRF={crf}, Max Bitrate={max_bitrate}")
            command = [
                "ffmpeg",
                "-i", input_path,
                "-vcodec", "libx264",
                "-crf", str(crf),
                "-preset", "medium",
                "-b:v", f"{max_bitrate}k",  # Adjust bitrate
                "-vf", "scale=1280:-2",  # Downscale to 720p if needed
                "-acodec", "aac",
                "-b:a", "128k",
                output_path,
            ]

            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            compressed_size_mb = os.path.getsize(output_path) / (1024 * 1024)
            if compressed_size_mb <= target_size_mb:
                logger.info(f"Compression successful: {compressed_size_mb:.2f} MB <= {target_size_mb} MB")
                cleanup_file(input_path)
                return True
            else:
                logger.warning(f"Compressed file exceeds size limit: {compressed_size_mb:.2f} MB > {target_size_mb} MB")
                cleanup_file(output_path)
        except Exception as e:
            logger.error(f"Error during compression attempt {attempt + 1}: {e}", exc_info=True)

        # Adjust parameters for the next attempt
        crf += 2
        max_bitrate -= 500

    logger.error(f"Failed to compress {input_path} below {target_size_mb} MB after {max_attempts} attempts.")
    return False
