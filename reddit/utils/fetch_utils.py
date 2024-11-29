import logging
from typing import List, Optional, Set
import asyncprawcore
from asyncpraw.models import Subreddit, Submission
from reddit import get_reddit_client
from reddit.config import Paths, MediaConfig

logger = logging.getLogger(__name__)


async def fetch_and_validate_subreddit(subreddit_name: str, update) -> Optional[Subreddit]:
    """
    Fetch and validate a subreddit. Returns the subreddit object if successful, or None on failure.
    """
    subreddit_name = subreddit_name.strip()
    if not subreddit_name:
        logger.warning("Empty subreddit name provided.")
        await update.message.reply_text("Subreddit name cannot be empty.")
        return None

    try:
        logger.info(f"Loading subreddit: r/{subreddit_name}")
        reddit = await get_reddit_client()
        subreddit = await reddit.subreddit(subreddit_name)
        await subreddit.load()
        logger.info(f"Successfully loaded subreddit: r/{subreddit_name}")
        return subreddit
    except asyncprawcore.exceptions.Redirect:
        await _log_and_notify(update, f"Subreddit r/{subreddit_name} does not exist.", warning=True)
    except asyncprawcore.exceptions.Forbidden:
        await _log_and_notify(update, f"Access to subreddit r/{subreddit_name} is restricted.", warning=True)
    except Exception as e:
        logger.error(f"Unexpected error loading subreddit r/{subreddit_name}: {e}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred while accessing r/{subreddit_name}.")
    return None


def filter_duplicates(posts: List[Submission], processed_post_ids: Set[str]) -> List[Submission]:
    """
    Filter out duplicate posts based on their IDs.
    """
    unique_posts = [post for post in posts if post.id not in processed_post_ids]
    logger.debug(f"Filtered {len(posts) - len(unique_posts)} duplicate posts.")
    processed_post_ids.update(post.id for post in unique_posts)
    return unique_posts


def log_filtered_posts(subreddit_name: str, posts: List[Submission]) -> None:
    """
    Log details of filtered posts.
    """
    if posts:
        logger.info(f"Filtered {len(posts)} unique media posts from r/{subreddit_name}:")
        for post in posts:
            logger.info(f"Post ID: {post.id}, Title: {post.title}, URL: {post.url}")
    else:
        logger.info(f"No unique media posts matched the criteria in r/{subreddit_name}.")


async def log_all_posts_to_file(subreddit_name: str, posts: List[Submission]) -> None:
    """
    Logs all fetched posts (up to POST_LIMIT) into a text file, including their flairs.
    Exclusively handles Submission objects.
    """
    if not posts:
        logger.info(f"No posts to log for subreddit: r/{subreddit_name}")
        return

    try:
        with open(Paths.FETCHED_POSTS_LOG_PATH, "a", encoding="utf-8") as file:
            file.write(f"Subreddit: r/{subreddit_name}\nTotal Posts: {len(posts)}\n")
            for post in posts:
                flair = post.link_flair_text or "No Flair"
                file.write(f"Post ID: {post.id}, Title: {post.title}, URL: {post.url}, Flair: {flair}\n")
            file.write("\n" + "-" * 50 + "\n\n")
        logger.info(f"Logged {len(posts)} posts from r/{subreddit_name} to file.")
    except Exception as e:
        logger.error(f"Failed to log posts for r/{subreddit_name}: {e}", exc_info=True)


async def get_sorted_subreddit_posts(
    subreddit: Subreddit, sort: str, time_filter: Optional[str] = None
) -> List[Submission]:
    """
    Fetch posts sorted by the specified criteria (e.g., 'hot', 'top').
    Exclusively returns Submission objects.
    """
    logger.info(f"Fetching sorted posts: r/{subreddit.display_name}, sort: {sort}, time filter: {time_filter}")
    try:
        posts = await _fetch_subreddit_posts(subreddit, sort, time_filter)
        await log_all_posts_to_file(subreddit.display_name, posts)
        return posts
    except Exception as e:
        logger.error(f"Error fetching sorted posts from r/{subreddit.display_name}: {e}", exc_info=True)
        return []


async def _fetch_subreddit_posts(subreddit: Subreddit, sort: str, time_filter: Optional[str]) -> List[Submission]:
    """
    Helper function to fetch posts from a subreddit using sorting criteria.
    """
    if sort == "top" and time_filter:
        return [post async for post in subreddit.top(time_filter=time_filter, limit=MediaConfig.POST_LIMIT)]
    return [post async for post in subreddit.hot(limit=MediaConfig.POST_LIMIT)]


def validate_submission_objects(posts: List[Submission], context: str = "") -> None:
    """
    Validates that all items in the provided list are Submission objects.
    Logs warnings for any unexpected types.

    Args:
        posts (List[Submission]): The list of posts to validate.
        context (str): Contextual information for logging (e.g., "fetched posts").
    """
    for post in posts:
        if not isinstance(post, Submission):
            logger.warning(f"Unexpected type in {context}: {type(post)}")


async def _fetch_search_results(
    subreddit: Subreddit, query: str, sort: str, time_filter: Optional[str]
) -> List[Submission]:
    """
    Helper function to fetch search results from a subreddit.
    """
    return [
        post
        async for post in subreddit.search(
            query=query,
            sort=sort,
            time_filter=time_filter or "all",
            limit=MediaConfig.POST_LIMIT,
        )
    ]


async def _log_and_notify(update, message: str, warning: bool = False) -> None:
    """
    Helper function to log and send notifications to the user.
    """
    if warning:
        logger.warning(message)
    else:
        logger.info(message)
    await update.message.reply_text(message)