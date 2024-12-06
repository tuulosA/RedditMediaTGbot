#__init__.py
from bot.config import RedditConfig

# Global Reddit client instance
REDDIT_CLIENT = None


async def get_reddit_client():
    """
    Returns a shared instance of the Reddit client, initializing it if necessary.
    """
    global REDDIT_CLIENT
    if REDDIT_CLIENT is None:
        REDDIT_CLIENT = await RedditConfig.initialize_reddit()
    return REDDIT_CLIENT
