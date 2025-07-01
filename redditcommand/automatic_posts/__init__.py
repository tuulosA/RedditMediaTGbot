"""
redditcommand.automatic_posts package initializer
"""

# Top media post scheduling (daily, weekly, etc.)
from .top_post import (
    send_daily_top_post_command,
    send_weekly_top_post_command,
    send_monthly_top_post_command,
    send_yearly_top_post_command,
    send_all_time_top_post_command,
    send_daily_top_post_job,
    send_weekly_top_post_job,
    send_monthly_top_post_job,
    send_yearly_top_post_job,
)

# Followed user monitoring
from .follow_user import check_and_send_new_user_posts
