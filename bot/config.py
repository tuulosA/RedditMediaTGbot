import os
import asyncpraw
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class RedditConfig:
    @staticmethod
    def load_reddit_config():
        """
        Loads Reddit API credentials from environment variables.
        """
        required_keys = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT", "REDDIT_USERNAME", "REDDIT_PASSWORD"]
        config = {key: os.getenv(key) for key in required_keys}

        # Ensure all required keys are present
        missing_keys = [key for key, value in config.items() if not value]
        if missing_keys:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_keys)}")

        return config

    @staticmethod
    async def initialize_reddit():
        """
        Initializes and returns an asyncpraw Reddit client.
        """
        config = RedditConfig.load_reddit_config()
        return asyncpraw.Reddit(
            client_id=config["REDDIT_CLIENT_ID"],
            client_secret=config["REDDIT_CLIENT_SECRET"],
            user_agent=config["REDDIT_USER_AGENT"],
            username=config["REDDIT_USERNAME"],
            password=config["REDDIT_PASSWORD"],
        )


class TimeoutConfig:
    DOWNLOAD_TIMEOUT = 300


class RetryConfig:
    RETRY_ATTEMPTS = 3
    MAX_RETRIES = 2


class MediaConfig:
    MAX_FILE_SIZE_MB = 50
    DEFAULT_SEMAPHORE_LIMIT = 3
    MAX_MEDIA_COUNT = 5
    POST_LIMIT = 50


class Messages:
    USAGE_MESSAGE = "Usage: /r [all/year/month/week] [subreddit(s)] [term(s)] [count] [image/video]"
    INVALID_FORMAT_MESSAGE = "Invalid command format. Example: /r [time_filter] [subreddits] [search_terms] [media_type] [media_count]"
    MAX_COUNT_EXCEEDED_MESSAGE = f"Maximum of {MediaConfig.MAX_MEDIA_COUNT} media files can be fetched at a time."


class Paths:
    BLACKLIST_FILE = os.path.join(os.getcwd(), "dead_links.json")
