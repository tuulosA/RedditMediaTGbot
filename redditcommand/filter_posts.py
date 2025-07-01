# Updated filter_posts.py to use refactored FilterUtils class

import logging
from random import sample
from typing import List, Optional, Set
from asyncpraw.models import Submission

from redditcommand.utils.filter_utils import FilterUtils

logger = logging.getLogger(__name__)


async def filter_media_posts(
    posts: List[Submission],
    subreddit_name: str,
    media_type: Optional[str] = None,
    media_count: int = 1,
    processed_urls: Optional[Set[str]] = None,
) -> List[Submission]:
    logger.info(f"Filtering r/{subreddit_name} | Total posts: {len(posts)}")
    if not posts:
        logger.warning(f"No posts to filter in r/{subreddit_name}")
        return []

    processed_urls = processed_urls or set()
    skipped = {"non-media": 0, "blacklisted": 0, "processed": 0, "gfycat": 0, "wrong type": 0}
    filtered = []

    for post in posts:
        reason = FilterUtils.should_skip(post, processed_urls, media_type)
        if reason:
            skipped[reason] += 1
        else:
            await FilterUtils.attach_metadata(post)
            filtered.append(post)

    FilterUtils.log_skips(skipped)

    if not filtered:
        logger.info(f"No matching {media_type or 'media'} posts in r/{subreddit_name}")
        return []

    selected = sample(filtered, min(media_count, len(filtered)))
    logger.info(f"Selected {len(selected)} post(s) from r/{subreddit_name}")
    return selected