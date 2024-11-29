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
        Returns:
            dict: A dictionary containing Reddit API credentials.
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
    FETCH_TIMEOUT = 120
    DOWNLOAD_TIMEOUT = 300

class RetryConfig:
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 2
    MAX_RETRIES = 2

class MediaConfig:
    MAX_FILE_SIZE_MB = 50
    DEFAULT_SEMAPHORE_LIMIT = 10
    MAX_MEDIA_COUNT = 5
    POST_LIMIT = 100

class Messages:
    USAGE_MESSAGE = "Usage: /r [all/year/month/week] [subreddit(s)] [term(s)] [count] [image/video]"
    INVALID_FORMAT_MESSAGE = "Invalid command format. Example: /r [time_filter] [subreddits] [search_terms] [media_type] [media_count]"
    MAX_MEDIA_COUNT_MESSAGE = "Maximum of 5 files can be requested."

class Paths:
    BLACKLIST_FILE = os.path.join(os.getcwd(), "dead_links.json")
    FETCHED_POSTS_LOG_PATH = os.path.join(os.getcwd(), "fetched_posts_log.txt")
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "reddit_config.json")

