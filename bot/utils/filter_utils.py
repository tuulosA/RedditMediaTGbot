import logging
from typing import Optional, Set
from bot.utils.blacklist_manager import is_blacklisted
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)


def should_skip_post(post: Submission, processed_urls: Set[str], media_type: Optional[str]) -> Optional[str]:
    """
    Determines if a post should be skipped and returns the reason.
    """
    if not post.url or not is_valid_media_url(post.url):
        return "non-media"
    if is_blacklisted(post.url):
        return "blacklisted"
    if post.url in processed_urls:
        return "processed"
    if is_gfycat_url(post.url):
        return "gfycat"
    if not filter_posts_by_type(post.url, media_type):
        return "wrong type"
    return None


def is_valid_media_url(url: str) -> bool:
    """
    Validates if a URL is a supported media type or pattern.
    """
    valid_extensions = (".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm", ".gifv")
    supported_patterns = ["/gallery/", "v.redd.it", "i.redd.it", "imgur.com"]
    return url.lower().endswith(valid_extensions) or any(pattern in url for pattern in supported_patterns)


def filter_posts_by_type(url: str, media_type: Optional[str]) -> bool:
    """
    Filters posts based on the specified media type.
    """
    url_lower = url.lower()
    return (
        not media_type or
        (media_type == "image" and url_lower.endswith(("jpg", "jpeg", "png"))) or
        (media_type == "video" and url_lower.endswith(("mp4", "webm", "gifv", "gif"))) or
        ("/gallery/" in url_lower and media_type == "image") or
        ("v.redd.it" in url_lower and media_type == "video")
    )


def is_gfycat_url(url: str) -> bool:
    """
    Check if a URL is a Gfycat URL.
    """
    return "gfycat.com" in url.lower()


def attach_post_metadata(post: Submission) -> None:
    """
    Attach metadata to a Submission object.
    """
    post.metadata = {
        "title": (post.title or "Unknown")[:100],
        "url": post.url,
        "id": post.id,
        "link_flair_text": (post.link_flair_text or "None")[:50],
        "file_path": None,
    }


def log_skipped_reasons(skip_reasons: dict) -> None:
    """
    Logs a summary of skipped reasons.
    """
    logger.info("Skipped posts summary: " + ", ".join(f"{reason}: {count}" for reason, count in skip_reasons.items()))
