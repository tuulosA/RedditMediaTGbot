# redditcommand/utils/fetch_utils.py

import logging
import asyncio
import random

from typing import List, Optional, Set, Tuple
from asyncpraw.models import Subreddit, Submission

from redditcommand.config import RedditClientManager, MediaConfig

logger = logging.getLogger(__name__)


class SubredditFetcher:
    @staticmethod
    async def fetch_and_validate(subreddit_name: str, update) -> Optional[Subreddit]:
        if subreddit_name.strip().lower() == "random":
            return await SubredditFetcher._fetch_random(update)

        if not subreddit_name.strip():
            await SubredditFetcher._log_and_notify(update, "Subreddit name cannot be empty.", warning=True)
            return None

        try:
            reddit = await RedditClientManager.get_client()
            subreddit = await reddit.subreddit(subreddit_name)
            await subreddit.load()
            logger.info(f"Loaded subreddit: r/{subreddit_name}")
            return subreddit
        except Exception as e:
            return await SubredditFetcher._handle_error(e, subreddit_name, update)

    @staticmethod
    async def _fetch_random(update) -> Optional[Subreddit]:
        try:
            reddit = await RedditClientManager.get_client()
            subreddit = await reddit.random_subreddit()
            await subreddit.load()
            logger.info(f"Loaded random subreddit: r/{subreddit.display_name}")
            return subreddit
        except Exception as e:
            logger.error(f"Random subreddit fetch failed: {e}", exc_info=True)
            await SubredditFetcher._log_and_notify(update, "Failed to load a random subreddit.", warning=True)
            return None

    @staticmethod
    async def _handle_error(e: Exception, subreddit_name: str, update) -> None:
        error_map = {
            "Redirect": "Subreddit does not exist.",
            "Forbidden": "Access to this subreddit is restricted.",
        }
        error_message = error_map.get(e.__class__.__name__, str(e))
        return await SubredditFetcher._log_and_notify(update, f"r/{subreddit_name}: {error_message}", warning=True)

    @staticmethod
    async def _log_and_notify(update, message: str, warning: bool = False) -> None:
        if warning:
            logger.warning(message)
        else:
            logger.info(message)
        await update.message.reply_text(message)


class RedditPostFetcher:
    @staticmethod
    async def fetch_sorted(subreddit: Subreddit, sort: str, time_filter: Optional[str] = None) -> List[Submission]:
        try:
            if sort == "top" and time_filter:
                return [post async for post in subreddit.top(time_filter=time_filter, limit=MediaConfig.POST_LIMIT)]
            return [post async for post in subreddit.hot(limit=MediaConfig.POST_LIMIT)]
        except Exception as e:
            logger.error(f"Error fetching sorted posts: {e}", exc_info=True)
            return []

    @staticmethod
    async def search(subreddit: Subreddit, query: str, sort: str, time_filter: Optional[str]) -> List[Submission]:
        try:
            return [
                post async for post in subreddit.search(
                    query=query,
                    sort=sort,
                    time_filter=time_filter or "all",
                    limit=MediaConfig.POST_LIMIT,
                )
            ]
        except Exception as e:
            logger.error(f"Search error for query '{query}': {e}", exc_info=True)
            return []

    @staticmethod
    async def filter_duplicates(posts: List[Submission], seen_ids: Set[str]) -> List[Submission]:
        def _dedupe():
            unique = [p for p in posts if p.id not in seen_ids]
            seen_ids.update(p.id for p in unique)
            return unique

        result = await asyncio.to_thread(_dedupe)
        logger.debug(f"Filtered {len(posts) - len(result)} duplicates")
        return result


class RandomSearch:
    @staticmethod
    async def run(reddit, search_terms, sort, time_filter, update):
        try:
            if search_terms:
                query = " ".join(search_terms)
                logger.info(f"Running search for: '{query}' in r/all")
                subreddit = await reddit.subreddit("all")
                posts = [
                    post async for post in subreddit.search(
                        query=query,
                        sort=sort,
                        time_filter=time_filter or "all",
                        limit=MediaConfig.POST_LIMIT
                    )
                ]
                return posts, subreddit if posts else ([], subreddit)

            subreddits = [sub async for sub in reddit.subreddits.popular(limit=100)]
            if not subreddits:
                logger.warning("No popular subreddits found.")
                await update.message.reply_text("Failed to fetch random subreddit.")
                return [], None

            subreddit = random.choice(subreddits)
            logger.info(f"Fallback: selected r/{subreddit.display_name}")
            return [], subreddit

        except Exception as e:
            logger.error(f"Random search failure: {e}", exc_info=True)
            await update.message.reply_text("Random subreddit fetch failed.")
            return [], None


class FetchOrchestrator:
    @staticmethod
    async def get_posts(reddit, subreddit_name: str, search_terms, sort, time_filter, update) -> Tuple[List[Submission], Optional[str]]:
        if subreddit_name.lower() == "random":
            posts, subreddit = await RandomSearch.run(reddit, search_terms, sort, time_filter, update)
        else:
            subreddit = await SubredditFetcher.fetch_and_validate(subreddit_name, update)
            posts = []

        if subreddit and not posts:
            query = " ".join(search_terms) if search_terms else None
            posts = (
                await RedditPostFetcher.search(subreddit, query, sort, time_filter)
                if query else await RedditPostFetcher.fetch_sorted(subreddit, sort, time_filter)
            )

        display_name = getattr(subreddit, "display_name", None)
        return posts, display_name