import asyncio
import logging
from bot import get_reddit_client
from bot.fetch import fetch_posts_to_list
from bot.media_handler import process_media_batch
from bot.utils.pipeline_utils import initialize_client, notify_user, log_summary, validate_subreddits
from bot.config import MediaConfig, RetryConfig

logger = logging.getLogger(__name__)


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
            filtered_media = await fetch_posts_to_list(
                subreddit_names=subreddit_names,
                search_terms=search_terms,
                sort=sort,
                time_filter=time_filter,
                media_type=media_type,
                media_count=remaining_count,
                semaphore=fetch_semaphore,
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
