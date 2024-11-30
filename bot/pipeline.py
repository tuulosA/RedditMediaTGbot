import asyncio
import logging
from bot import get_reddit_client
from bot.fetch import fetch_posts_to_list
from bot.media_handler import process_media_batch
from bot.utils.pipeline_utils import (
    initialize_client,
    notify_user,
    log_summary,
    validate_subreddits,
    clear_fetched_posts_log,
)
from bot.config import TimeoutConfig, MediaConfig, RetryConfig

logger = logging.getLogger(__name__)


async def fetch_and_filter_media(
    subreddit_names,
    search_terms,
    sort,
    time_filter,
    media_type,
    remaining_count,
    fetch_semaphore,
    update,
    processed_urls,
    include_comments=False,
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

        filtered_media = [
            post for post in media_posts if post.url not in processed_urls
        ]
        logger.info(f"Filtered {len(media_posts) - len(filtered_media)} already processed posts.")
        return filtered_media
    except asyncio.TimeoutError:
        logger.error("Timeout occurred while fetching media posts.")
        raise RuntimeError("Fetching media posts timed out. Please try again later.")
    except Exception as e:
        logger.error(f"Error fetching media posts: {e}", exc_info=True)
        raise RuntimeError("An error occurred while fetching media posts. Please try again.")


async def pipeline(
    update,
    subreddit_names: list[str],
    search_terms: list[str],
    sort: str = "hot",
    time_filter: str = None,
    media_count: int = 1,
    media_type: str = None,
    include_comments: bool = False,
    fetch_semaphore_limit: int = MediaConfig.DEFAULT_SEMAPHORE_LIMIT,
):
    """
    Main pipeline for fetching and processing media posts from Reddit.
    """
    clear_fetched_posts_log()
    logger.info(
        f"Starting pipeline with subreddits: {', '.join(subreddit_names)}, "
        f"search terms: {search_terms}, sort: {sort}, "
        f"time filter: {time_filter}, media count: {media_count}, include_comments={include_comments}"
    )

    fetch_semaphore = asyncio.Semaphore(fetch_semaphore_limit)
    total_processed, retry_attempts, backoff = 0, 0, 1
    successfully_sent_posts, processed_urls = [], set()

    try:
        # Initialize Reddit client and validate subreddits
        reddit_instance = await initialize_client(get_reddit_client)
        valid_subreddits = await validate_subreddits(reddit_instance, subreddit_names)
        if not valid_subreddits:
            await notify_user(update, "None of the specified subreddits exist or are accessible.")
            logger.warning(f"Invalid subreddits: {', '.join(subreddit_names)}")
            return

        if len(valid_subreddits) < len(subreddit_names):
            invalid_subreddits = set(subreddit_names) - set(valid_subreddits)
            await notify_user(update, f"Some subreddits are invalid or inaccessible: {', '.join(invalid_subreddits)}")
            logger.warning(f"Invalid subreddits: {', '.join(invalid_subreddits)}")
            subreddit_names = valid_subreddits

        # Main processing loop
        while total_processed < media_count and retry_attempts < RetryConfig.MAX_RETRIES:
            remaining_count = media_count - total_processed
            logger.info(f"Fetching posts. Total processed: {total_processed}/{media_count}")

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
                logger.warning(f"No new media found. Retrying ({retry_attempts + 1}/{RetryConfig.MAX_RETRIES})...")
                retry_attempts += 1
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)  # Exponential backoff, capped at 30 seconds
                continue

            processed_urls.update(post.url for post in filtered_media)
            processed = await process_media_batch(filtered_media, reddit_instance, update, include_comments)
            successfully_sent_posts.extend(processed)
            total_processed += len(processed)

        if total_processed < media_count:
            await notify_user(update, f"Only {total_processed}/{media_count} unique media posts found.")

        # Log all posts and summary
        from bot.utils.fetch_utils import log_all_posts_to_file
        for subreddit in subreddit_names:
            await log_all_posts_to_file(subreddit, successfully_sent_posts)
        log_summary(successfully_sent_posts)
        logger.info(f"Pipeline completed: {total_processed}/{media_count} media posts processed.")

    except RuntimeError as e:
        await notify_user(update, str(e))
    except Exception as e:
        logger.error(f"Unexpected error in pipeline: {e}", exc_info=True)
        await notify_user(update, "An unexpected error occurred. Please try again.")
    finally:
        logger.info("Pipeline execution finished.")
