import asyncio
import logging
from bot import get_reddit_client
from bot.fetch import fetch_posts_to_list
from bot.media_handler import process_media_batch
from bot.utils.pipeline_utils import initialize_client, notify_user, log_summary, validate_subreddits
from bot.config import TimeoutConfig, MediaConfig, RetryConfig

logger = logging.getLogger(__name__)


async def fetch_and_filter_media(
    subreddit_names, search_terms, sort, time_filter, media_type,
    remaining_count, fetch_semaphore, update, processed_urls, include_comments=False
):
    """
    Fetches media posts and filters out already processed ones.
    """
    try:
        media_posts = await asyncio.wait_for(
            fetch_posts_to_list(
                subreddit_names=subreddit_names,
                semaphore=fetch_semaphore,
                search_terms=search_terms,
                sort=sort,
                time_filter=time_filter,
                media_type=media_type,
                media_count=remaining_count,
                update=update,
                include_comments=include_comments,
            ),
            timeout=TimeoutConfig.FETCH_TIMEOUT,
        )
        filtered = [post for post in media_posts if post.url not in processed_urls]
        logger.info(f"Filtered out {len(media_posts) - len(filtered)} duplicate posts.")
        return filtered
    except asyncio.TimeoutError:
        raise RuntimeError("Fetching media posts timed out. Please try again later.")
    except Exception as e:
        raise RuntimeError(f"Error fetching media posts: {e}")


async def pipeline(
    update, subreddit_names: list[str], search_terms: list[str],
    sort: str = "hot", time_filter: str = None, media_count: int = 1,
    media_type: str = None, include_comments: bool = False,
    fetch_semaphore_limit: int = MediaConfig.DEFAULT_SEMAPHORE_LIMIT,
):
    """
    Main pipeline for fetching and processing media posts from Reddit.
    """
    logger.info(f"Starting pipeline for subreddits: {', '.join(subreddit_names)}")
    fetch_semaphore = asyncio.Semaphore(fetch_semaphore_limit)
    processed_urls, total_processed, backoff = set(), 0, 1
    successfully_sent_posts = []

    try:
        reddit_instance = await initialize_client(get_reddit_client)
        valid_subreddits = await validate_subreddits(reddit_instance, subreddit_names)
        if not valid_subreddits:
            return await notify_user(update, "No valid or accessible subreddits provided.")

        subreddit_names = valid_subreddits
        logger.info(f"Valid subreddits: {', '.join(subreddit_names)}")

        for _ in range(RetryConfig.MAX_RETRIES):
            remaining_count = media_count - total_processed
            if remaining_count <= 0:
                break

            logger.info(f"Fetching {remaining_count} more posts.")
            filtered_media = await fetch_and_filter_media(
                subreddit_names=subreddit_names,
                search_terms=search_terms,
                sort=sort,
                time_filter=time_filter,
                media_type=media_type,
                remaining_count=remaining_count,
                fetch_semaphore=fetch_semaphore,
                update=update,
                processed_urls=processed_urls,
                include_comments=include_comments,
            )

            if not filtered_media:
                logger.warning(f"No new media found. Retrying after backoff ({backoff}s).")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Exponential backoff
                continue

            processed_urls.update(post.url for post in filtered_media)
            processed = await process_media_batch(filtered_media, reddit_instance, update, include_comments)
            successfully_sent_posts.extend(processed)
            total_processed += len(processed)

        if total_processed < media_count:
            await notify_user(update, f"Only {total_processed}/{media_count} posts found.")

        log_summary(successfully_sent_posts)
        logger.info("Pipeline completed successfully.")
    except RuntimeError as e:
        await notify_user(update, str(e))
        logger.error(f"Pipeline error: {e}")
    except Exception as e:
        await notify_user(update, "An unexpected error occurred.")
        logger.error(f"Unexpected pipeline error: {e}", exc_info=True)
