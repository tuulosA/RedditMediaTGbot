import logging
from typing import List, Optional, Set
from asyncpraw.models import Subreddit, Submission
from bot import get_reddit_client
from bot.config import MediaConfig

logger = logging.getLogger(__name__)


async def fetch_and_validate_subreddit(subreddit_name: str, update) -> Optional[Subreddit]:
    """
    Fetch and validate a subreddit. Returns the subreddit object if successful, or None on failure.
    """
    if not subreddit_name.strip():
        return await _log_and_notify(update, "Subreddit name cannot be empty.", warning=True)

    try:
        reddit = await get_reddit_client()
        subreddit = await reddit.subreddit(subreddit_name)
        await subreddit.load()
        logger.info(f"Successfully loaded subreddit: r/{subreddit_name}")
        return subreddit
    except Exception as e:
        return await _handle_subreddit_error(e, subreddit_name, update)


def filter_duplicates(posts: List[Submission], processed_post_ids: Set[str]) -> List[Submission]:
    """
    Filter out duplicate posts based on their IDs.
    """
    unique_posts = [post for post in posts if post.id not in processed_post_ids]
    processed_post_ids.update(post.id for post in unique_posts)
    logger.debug(f"Filtered {len(posts) - len(unique_posts)} duplicate posts.")
    return unique_posts


async def get_sorted_subreddit_posts(
    subreddit: Subreddit, sort: str, time_filter: Optional[str] = None
) -> List[Submission]:
    """
    Fetch posts sorted by the specified criteria (e.g., 'hot', 'top').
    """
    try:
        if sort == "top" and time_filter:
            return [post async for post in subreddit.top(time_filter=time_filter, limit=MediaConfig.POST_LIMIT)]
        return [post async for post in subreddit.hot(limit=MediaConfig.POST_LIMIT)]
    except Exception as e:
        logger.error(f"Error fetching sorted posts: {e}", exc_info=True)
        return []


async def _fetch_search_results(
    subreddit: Subreddit, query: str, sort: str, time_filter: Optional[str]
) -> List[Submission]:
    """
    Helper function to fetch search results from a subreddit.
    """
    try:
        return [
            post
            async for post in subreddit.search(
                query=query,
                sort=sort,
                time_filter=time_filter or "all",
                limit=MediaConfig.POST_LIMIT,
            )
        ]
    except Exception as e:
        logger.error(f"Error fetching search results for query '{query}': {e}", exc_info=True)
        return []


async def _log_and_notify(update, message: str, warning: bool = False) -> None:
    """
    Log and send notifications to the user.
    """
    if warning:
        logger.warning(message)
    else:
        logger.info(message)
    await update.message.reply_text(message)


async def _handle_subreddit_error(e: Exception, subreddit_name: str, update) -> None:
    """
    Handle errors during subreddit validation.
    """
    error_map = {
        "Redirect": "Subreddit does not exist.",
        "Forbidden": "Access to this subreddit is restricted.",
    }
    error_message = error_map.get(e.__class__.__name__, str(e))
    return await _log_and_notify(update, f"r/{subreddit_name}: {error_message}", warning=True)
