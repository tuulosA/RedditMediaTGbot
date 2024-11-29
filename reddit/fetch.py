import asyncio
import random
import logging
from typing import Optional, List, Set
from reddit.filter_posts import filter_media_posts
from reddit.utils.fetch_utils import (
    fetch_and_validate_subreddit,
    filter_duplicates,
    log_filtered_posts,
    validate_submission_objects,
    _fetch_search_results,
    get_sorted_subreddit_posts
)
from reddit.config import MediaConfig
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
) -> List[Submission]:
    """
    Fetch media posts from multiple subreddits asynchronously with balanced distribution.
    Exclusively handles Submission objects.
    """
    semaphore = semaphore or asyncio.Semaphore(MediaConfig.DEFAULT_SEMAPHORE_LIMIT)
    invalid_subreddits = invalid_subreddits or set()
    processed_post_ids = set()
    remaining_posts = media_count
    media_list = []

    logger.info(
        f"Starting fetch for subreddits: {subreddit_names}, media count: {media_count}, sort: {sort}, "
        f"include_comments={include_comments}"
    )

    # Shuffle subreddits to ensure fair distribution
    random.shuffle(subreddit_names)

    # Create fetch tasks for valid subreddits
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
        for subreddit_name in subreddit_names
        if subreddit_name not in invalid_subreddits
    ]

    # Process tasks as they complete
    for task in asyncio.as_completed(fetch_tasks):
        try:
            media_posts = await task
            validate_submission_objects(media_posts, context="media_posts")

            if media_posts:
                # Extend results up to the remaining required count
                media_list.extend(media_posts[:remaining_posts])
                remaining_posts -= len(media_posts)

                if remaining_posts <= 0:
                    break
        except Exception as e:
            logger.error(f"Error in fetch task: {e}")

    logger.info(f"Fetched {len(media_list)} total media posts across all subreddits.")
    return media_list[:media_count]  # Ensure hard limit


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
            logger.debug(f"Validating subreddit: r/{subreddit_name}")
            subreddit = await fetch_and_validate_subreddit(subreddit_name, update)
            if not subreddit:
                logger.warning(f"Subreddit validation failed: r/{subreddit_name}")
                return []

            logger.info(f"Fetching posts from r/{subreddit_name} with search terms: {search_terms}")
            posts = await fetch_posts(subreddit, search_terms, sort, time_filter)
            validate_submission_objects(posts, context="fetched posts")  # Consolidated validation

            if not posts:
                logger.info(f"No posts fetched from r/{subreddit_name}")
                return []

            filtered_posts = await filter_media_posts(posts, subreddit_name, media_type, target_count)
            validate_submission_objects(filtered_posts, context="filtered posts")  # Consolidated validation

            unique_posts = filter_duplicates(filtered_posts, processed_post_ids)
            validate_submission_objects(unique_posts, context="unique posts")  # Consolidated validation

            log_filtered_posts(subreddit_name, unique_posts)
            logger.info(f"Extracted {len(unique_posts)} unique posts from r/{subreddit_name}")

            return unique_posts
        except asyncio.TimeoutError:
            logger.error(f"Timeout occurred while processing r/{subreddit_name}")
            return []
        except Exception as e:
            logger.error(f"Error fetching posts from r/{subreddit_name}: {e}", exc_info=True)
            return []


async def fetch_posts(
    subreddit: Subreddit, search_terms: List[str], sort: str, time_filter: Optional[str]
) -> List[Submission]:
    """
    Fetch posts from a subreddit using search terms or sorted criteria.
    Exclusively returns Submission objects.
    """
    try:
        if search_terms:
            search_query = " ".join(search_terms)
            logger.info(f"Searching r/{subreddit.display_name} with terms: {search_query}")
            posts = await _fetch_search_results(subreddit, search_query, sort, time_filter)
        else:
            logger.info(f"No search terms provided. Fetching sorted posts from r/{subreddit.display_name}.")
            posts = await get_sorted_subreddit_posts(subreddit, sort, time_filter)

        validate_submission_objects(posts, context="fetched posts")
        return posts
    except Exception as e:
        logger.error(f"Error fetching posts from r/{subreddit.display_name}: {e}", exc_info=True)
        return []
