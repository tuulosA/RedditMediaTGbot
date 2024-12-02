import logging
from typing import List, Optional, Set
from random import sample
from bot.utils.filter_utils import should_skip_post, attach_post_metadata, log_skipped_reasons
from asyncpraw.models import Submission

logger = logging.getLogger(__name__)


async def filter_media_posts(
    posts: List[Submission],
    subreddit_name: str,
    media_type: Optional[str] = None,
    media_count: int = 1,
    processed_urls: Set[str] = None,
) -> List[Submission]:
    """
    Filters posts based on media type, validity, and other criteria.
    """
    logger.info(f"Starting filter for r/{subreddit_name}. Total posts: {len(posts) if posts else 0}")
    if not posts:
        logger.warning(f"No posts to filter in r/{subreddit_name}")
        return []

    processed_urls = processed_urls or set()
    skip_reasons = {"non-media": 0, "blacklisted": 0, "processed": 0, "gfycat": 0, "wrong type": 0}

    filtered_posts = [
        attach_post_metadata(post) or post
        for post in posts
        if not (reason := should_skip_post(post, processed_urls, media_type)) or skip_reasons.update({reason: skip_reasons[reason] + 1})
    ]

    log_skipped_reasons(skip_reasons)

    if not filtered_posts:
        logger.info(f"No {media_type or 'media'} posts found in r/{subreddit_name}.")
        return []

    selected_posts = sample(filtered_posts, min(len(filtered_posts), media_count))
    logger.info(f"Selected {len(selected_posts)} posts from r/{subreddit_name}.")
    return selected_posts
