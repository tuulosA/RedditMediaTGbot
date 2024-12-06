#fetch.py
import asyncio
import random
import logging
from typing import Optional, List, Set
from bot.filter_posts import filter_media_posts
from bot.utils.fetch_utils import (
    fetch_and_validate_subreddit,
    filter_duplicates,
    _fetch_search_results,
    get_sorted_subreddit_posts
)
from bot.config import MediaConfig
from asyncpraw.models import Subreddit, Submission

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
    """
    Fetch and filter media posts from multiple subreddits asynchronously.
    Removes already processed posts based on `processed_urls`.
    """
    semaphore = semaphore or asyncio.Semaphore(MediaConfig.DEFAULT_SEMAPHORE_LIMIT)
    invalid_subreddits = invalid_subreddits or set()
    processed_urls = processed_urls or set()
    processed_post_ids = set()
    media_posts = []

    logger.info(f"Starting fetch for subreddits: {', '.join(subreddit_names)}, media count: {media_count}, sort: {sort}")

    if invalid_subreddits:
        logger.warning(f"Skipping invalid subreddits: {', '.join(invalid_subreddits)}")

    # Shuffle subreddits to ensure fair distribution
    random.shuffle(subreddit_names)

    # Create fetch tasks
    fetch_tasks = [
        fetch_from_subreddit(
            subreddit_name=subreddit_name,
            search_terms=search_terms,
            sort=sort,
            time_filter=time_filter,
            media_type=media_type,
            target_count=max(1, media_count // len(subreddit_names)),
            processed_post_ids=processed_post_ids,
            semaphore=semaphore,
            update=update,
        )
        for subreddit_name in subreddit_names if subreddit_name not in invalid_subreddits
    ]

    # Gather results
    results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    for subreddit_name, result in zip(subreddit_names, results):
        if isinstance(result, Exception):
            logger.error(f"Error in fetch task for subreddit '{subreddit_name}': {result}", exc_info=True)
        elif isinstance(result, list):
            media_posts.extend(result)
        else:
            logger.warning(f"Unexpected result type for subreddit '{subreddit_name}': {type(result)}")

    # Filter out already processed URLs
    filtered_posts = [post for post in media_posts if post.url not in processed_urls]
    logger.info(f"Filtered out {len(media_posts) - len(filtered_posts)} already processed posts.")
    logger.info(f"Total unique posts fetched: {len(filtered_posts)}")

    return filtered_posts[:media_count]  # Return only the requested count


async def fetch_from_subreddit(
    subreddit_name: str,
    search_terms: List[str],
    sort: str,
    time_filter: Optional[str],
    media_type: Optional[str],
    target_count: int,
    processed_post_ids: Set[str],
    semaphore: asyncio.Semaphore,
    update,
) -> List[Submission]:
    """
    Fetch posts from a single subreddit, filter them, and remove duplicates.
    Exclusively returns Submission objects.
    """
    async with semaphore:
        try:
            subreddit = await fetch_and_validate_subreddit(subreddit_name, update)
            if not subreddit:
                logger.warning(f"Subreddit validation failed for: {subreddit_name}")
                return []

            posts = await fetch_posts(subreddit, search_terms, sort, time_filter)
            if not posts:
                logger.info(f"No posts found in subreddit: {subreddit_name}")
                return []

            filtered_posts = await filter_media_posts(posts, subreddit_name, media_type, target_count)
            unique_posts = await filter_duplicates(filtered_posts, processed_post_ids)
            logger.info(f"Fetched {len(unique_posts)} unique posts from r/{subreddit_name}")
            return unique_posts
        except Exception as e:
            logger.error(f"Error fetching from subreddit '{subreddit_name}': {e}", exc_info=True)
            return []


async def fetch_posts(
    subreddit: Subreddit, search_terms: List[str], sort: str, time_filter: Optional[str]
) -> List[Submission]:
    """
    Fetch posts from a subreddit using search terms or sorted criteria.
    """
    try:
        if search_terms:
            query = " ".join(search_terms)
            logger.info(f"Searching r/{subreddit.display_name} with terms: {query}")
            return await _fetch_search_results(subreddit, query, sort, time_filter)
        else:
            logger.info(f"Fetching sorted posts (sort={sort}, time_filter={time_filter}) from r/{subreddit.display_name}.")
            return await get_sorted_subreddit_posts(subreddit, sort, time_filter)
    except Exception as e:
        logger.error(f"Error fetching posts from r/{subreddit.display_name}: {e}", exc_info=True)
        return []
