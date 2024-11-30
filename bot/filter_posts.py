import logging
from typing import List, Optional, Set
from random import sample
from bot.utils.filter_utils import (
    should_skip_post,
    attach_post_metadata,
    log_skipped_reasons
)
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
    Filters posts based on media type, validity, and other criteria, while considering processed URLs.
    Exclusively processes Submission objects.
    """
    logger.info(f"Starting: r/{subreddit_name}. Total posts: {len(posts) if posts else 0}")

    if not posts:
        logger.warning(f"No posts provided for subreddit: r/{subreddit_name}")
        return []

    processed_urls = processed_urls or set()
    filtered_posts = []
    skip_reasons = {"non-media": 0, "blacklisted": 0, "processed": 0, "gfycat": 0, "wrong type": 0}

    for post in posts:
        try:
            skip_reason = should_skip_post(post, processed_urls, media_type)
            if skip_reason:
                skip_reasons[skip_reason] += 1
                logger.debug(f"Post skipped ({skip_reason}): {post.url}")
                continue

            attach_post_metadata(post)
            filtered_posts.append(post)
        except Exception as e:
            logger.error(f"Error processing post {post.id}: {e}", exc_info=True)

    log_skipped_reasons(skip_reasons)

    if not filtered_posts:
        logger.info(f"No {media_type or 'media'} posts found in r/{subreddit_name}.")
        return []

    # Randomly sample the required number of media posts
    selected_posts = sample(filtered_posts, min(len(filtered_posts), media_count))
    logger.info(f"Extracted {len(selected_posts)} media posts from r/{subreddit_name}.")
    return selected_posts
