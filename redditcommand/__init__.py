"""
redditcommand package initializer
"""

# Configuration
from .config import (
    RedditClientManager,
    MediaConfig,
    RetryConfig,
    TimeoutConfig,
    Messages,
)

# Core pipeline
from .pipeline import pipeline

# Fetching & filtering
from .fetch import fetch_posts_to_list
from .filter_posts import filter_media_posts

# Media processing
from .media_handler import process_media_batch

# Telegram commands
from .commands import (
    reddit_media_command,
    follow_user_command,
    unfollow_user_command,
    set_filter_command,
    clear_filter_command,
    list_followed_users_command,
)

# Automatic posts & background jobs
from .automatic_posts.follow_user import check_and_send_new_user_posts

# Media resolution
from .handle_direct_link import handle_direct_link
