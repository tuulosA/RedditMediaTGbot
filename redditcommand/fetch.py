# Updated fetch.py to use refactored fetch_utils classes

import asyncio
import random
import logging
from typing import Optional, List, Set
from asyncpraw.models import Submission

from .config import RedditClientManager, MediaConfig
from .filter_posts import filter_media_posts

from redditcommand.utils.fetch_utils import RedditPostFetcher, SubredditFetcher, RandomSearch

logger = logging.getLogger(__name__)


async def fetch_posts_to_list(
    subreddit_names: List[str],
    search_terms: Optional[List[str]] = None,
    sort: str = "hot",
    time_filter: Optional[str] = None,
    media_type: Optional[str] = None,
    media_count: int = 1,
    semaphore: Optional[asyncio.Semaphore] = None,
    update=None,
    invalid_subreddits: Optional[Set[str]] = None,
    include_comments: bool = False,
    processed_urls: Optional[Set[str]] = None,
) -> List[Submission]:
    semaphore = semaphore or asyncio.Semaphore(MediaConfig.DEFAULT_SEMAPHORE_LIMIT)
    invalid_subreddits = invalid_subreddits or set()
    processed_urls = processed_urls or set()
    processed_post_ids = set()
    media_posts = []

    logger.info(f"Fetching from: {', '.join(subreddit_names)} | media_count={media_count}, sort={sort}")

    valid_subreddits = [s for s in subreddit_names if s not in invalid_subreddits]
    random.shuffle(valid_subreddits)

    fetch_tasks = [
        fetch_posts_from_subreddit(
            subreddit_name=s,
            search_terms=search_terms,
            sort=sort,
            time_filter=time_filter,
            media_type=media_type,
            target_count=max(1, media_count // len(valid_subreddits)),
            processed_post_ids=processed_post_ids,
            semaphore=semaphore,
            update=update,
        )
        for s in valid_subreddits
    ]

    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
    for s_name, result in zip(valid_subreddits, results):
        if isinstance(result, Exception):
            logger.error(f"Subreddit '{s_name}' task failed: {result}", exc_info=True)
        elif isinstance(result, list):
            media_posts.extend(result)
        else:
            logger.warning(f"Unexpected result from subreddit '{s_name}': {type(result)}")

    filtered_posts = [post for post in media_posts if post.url not in processed_urls]
    logger.info(f"Removed {len(media_posts) - len(filtered_posts)} duplicates. Returning {len(filtered_posts)} posts.")

    return filtered_posts[:media_count]


async def fetch_posts_from_subreddit(
    subreddit_name: str,
    search_terms: Optional[List[str]],
    sort: str,
    time_filter: Optional[str],
    media_type: Optional[str],
    target_count: int,
    processed_post_ids: Set[str],
    semaphore: asyncio.Semaphore,
    update
) -> List[Submission]:
    async with semaphore:
        try:
            reddit = await RedditClientManager.get_client()
            posts = []
            subreddit = None

            if subreddit_name.lower() == "random":
                posts, subreddit = await RandomSearch.run(reddit, search_terms, sort, time_filter, update)
            else:
                subreddit = await SubredditFetcher.fetch_and_validate(subreddit_name, update)

            if not subreddit and not posts:
                logger.warning(f"Skipping invalid subreddit: {subreddit_name}")
                return []

            if subreddit and not posts:
                query = " ".join(search_terms) if search_terms else None
                logger.info(f"Querying r/{subreddit.display_name} | sort={sort}, time={time_filter}")
                posts = (
                    await RedditPostFetcher.search(subreddit, query, sort, time_filter)
                    if query else await RedditPostFetcher.fetch_sorted(subreddit, sort, time_filter)
                )

            if not posts:
                logger.info(f"No results from r/{subreddit.display_name if subreddit else 'all'}")
                return []

            filtered = await filter_media_posts(posts, subreddit.display_name, media_type, target_count)
            unique = await RedditPostFetcher.filter_duplicates(filtered, processed_post_ids)
            logger.info(f"r/{subreddit.display_name}: {len(unique)} unique posts")
            return unique

        except Exception as e:
            logger.error(f"Error from subreddit '{subreddit_name}': {e}", exc_info=True)
            return []