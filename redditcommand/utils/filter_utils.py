# redditcommand/utils/filter_utils.py

import logging
from typing import Optional, Set
from asyncpraw.models import Submission

from redditcommand.utils.logging_utils import setup_skip_logger, setup_accepted_logger
from redditcommand.utils.url_utils import is_valid_media_url, matches_media_type
from redditcommand.config import SkipReasons

logger = logging.getLogger(__name__)

skip_logger = setup_skip_logger()
accepted_logger = setup_accepted_logger()


class FilterUtils:
    @staticmethod
    async def attach_metadata(post: Submission) -> None:
        post.metadata = {
            "title": (post.title or "Unknown")[:100],
            "url": post.url,
            "id": post.id,
            "link_flair_text": (post.link_flair_text or "None")[:50],
            "file_path": None,
            "upvotes": post.score,
            "author": post.author.name if post.author else "[deleted]"
        }
        accepted_logger.info(
            f"[accepted] r/{getattr(post.subreddit, 'display_name', 'unknown')} | "
            f"ID: {post.id} | Title: {post.title[:50]} | Flair: {post.link_flair_text} | "
            f"Upvotes: {post.score} | Author: {post.metadata['author']} | Media URL: {post.url} | Post Link: https://reddit.com/comments/{post.id}"
        )

    @staticmethod
    def should_skip(
        post: Submission, processed_urls: Set[str], media_type: Optional[str]
    ) -> Optional[str]:
        url = post.url or ""
        reason = None

        if not url or not is_valid_media_url(url):
            reason = SkipReasons.NON_MEDIA
        elif url in processed_urls:
            reason = SkipReasons.PROCESSED
        elif FilterUtils.is_gfycat(url):
            reason = SkipReasons.GFYCAT
        elif not matches_media_type(url, media_type):
            reason = SkipReasons.WRONG_TYPE

        if reason:
            skip_logger.info(
                f"[{reason}] r/{getattr(post.subreddit, 'display_name', 'unknown')} | "
                f"ID: {post.id} | Title: {post.title[:50]} | Flair: {post.link_flair_text} | "
                f"Upvotes: {post.score} | Media URL: {post.url} | Post Link: https://reddit.com/comments/{post.id}"
            )
        return reason

    @staticmethod
    def is_gfycat(url: str) -> bool:
        return "gfycat.com" in url.lower()

    @staticmethod
    def log_skips(skip_reasons: dict) -> None:
        summary = ", ".join(f"{k}: {v}" for k, v in skip_reasons.items())
        logger.info(f"Skipped posts summary: {summary}")