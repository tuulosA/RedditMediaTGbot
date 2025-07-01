# filter_utils.py

import logging

from typing import Optional, Set
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)

# Skip logger to log rejected posts by reason
skip_logger = logging.getLogger("skip_debug")
skip_file_handler = logging.FileHandler("logs/skip_debug.log", mode="w", encoding="utf-8")
skip_file_handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
skip_logger.setLevel(logging.INFO)
skip_logger.addHandler(skip_file_handler)
skip_logger.propagate = False

# Accepted logger to log posts that passed filters
accepted_logger = logging.getLogger("accepted_debug")
accepted_file_handler = logging.FileHandler("logs/accepted_debug.log", mode="w", encoding="utf-8")
accepted_file_handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
accepted_logger.setLevel(logging.INFO)
accepted_logger.addHandler(accepted_file_handler)
accepted_logger.propagate = False


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

        if not url or not FilterUtils.is_valid_url(url):
            reason = "non-media"
        elif url in processed_urls:
            reason = "processed"
        elif FilterUtils.is_gfycat(url):
            reason = "gfycat"
        elif not FilterUtils.match_type(url, media_type):
            reason = "wrong type"

        if reason:
            skip_logger.info(
                f"[{reason}] r/{getattr(post.subreddit, 'display_name', 'unknown')} | "
                f"ID: {post.id} | Title: {post.title[:50]} | Flair: {post.link_flair_text} | "
                f"Upvotes: {post.score} | Media URL: {post.url} | Post Link: https://reddit.com/comments/{post.id}"
            )
        return reason

    @staticmethod
    def is_valid_url(url: str) -> bool:
        valid_exts = (".jpg", ".jpeg", ".png", ".gif", ".mp4", ".webm", ".gifv")
        valid_sources = [
            "/gallery/", "v.redd.it", "i.redd.it", "imgur.com", "streamable.com",
            "redgifs.com", "kick.com", "twitch.tv", "youtube.com", "youtu.be", "twitter.com", "x.com"
        ]
        return url.lower().endswith(valid_exts) or any(p in url for p in valid_sources)

    @staticmethod
    def match_type(url: str, media_type: Optional[str]) -> bool:
        url_lc = url.lower()
        return (
            not media_type or
            (media_type == "image" and url_lc.endswith(("jpg", "jpeg", "png"))) or
            (media_type == "video" and url_lc.endswith(("mp4", "webm", "gifv", "gif"))) or
            (media_type == "video" and "streamable.com" in url_lc) or
            (media_type == "video" and "redgifs.com" in url_lc) or
            ("/gallery/" in url_lc and media_type == "image") or
            ("v.redd.it" in url_lc and media_type == "video")
        )

    @staticmethod
    def is_gfycat(url: str) -> bool:
        return "gfycat.com" in url.lower()

    @staticmethod
    def log_skips(skip_reasons: dict) -> None:
        summary = ", ".join(f"{k}: {v}" for k, v in skip_reasons.items())
        logger.info(f"Skipped posts summary: {summary}")
