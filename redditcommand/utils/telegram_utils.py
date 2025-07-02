# redditcommand/utils/telegram_utils.py

from datetime import time, timezone, timedelta
from telegram.ext import Application, CommandHandler

from redditcommand.commands import RedditCommandHandler
from redditcommand.automatic_posts import (
    send_daily_top_post_command,
    send_weekly_top_post_command,
    send_monthly_top_post_command,
    send_yearly_top_post_command,
    send_all_time_top_post_command,
    send_daily_top_post_job,
    send_weekly_top_post_job,
    send_monthly_top_post_job,
    send_yearly_top_post_job,
    FollowUserScheduler
)

class TelegramRegistrar:
    LOCAL_TIME = timezone(timedelta(hours=3))

    @classmethod
    def register_command_handlers(cls, application: Application) -> None:
        commands = {
            'r': RedditCommandHandler.reddit_media_command,
            'follow': RedditCommandHandler.follow_user_command,
            'followed': RedditCommandHandler.list_followed_users_command,
            'unfollow': RedditCommandHandler.unfollow_user_command,
            'filter': RedditCommandHandler.set_filter_command,
            'clearfilters': RedditCommandHandler.clear_filter_command,

            'rtopday': send_daily_top_post_command,
            'rtopweek': send_weekly_top_post_command,
            'rtopmonth': send_monthly_top_post_command,
            'rtopyear': send_yearly_top_post_command,
            'rtopall': send_all_time_top_post_command
        }

        for cmd, handler in commands.items():
            application.add_handler(CommandHandler(cmd, handler))

    @classmethod
    def register_jobs(cls, application: Application, chat_id: int) -> None:
        job_queue = application.job_queue

        job_queue.run_daily(send_daily_top_post_job, time=time(17, tzinfo=cls.LOCAL_TIME), name="daily_top_post")
        job_queue.run_daily(send_weekly_top_post_job, time=time(17, tzinfo=cls.LOCAL_TIME), days=(0,), name="weekly_top_post")
        job_queue.run_daily(send_monthly_top_post_job, time=time(0, 0, tzinfo=cls.LOCAL_TIME), name="monthly_top_post")
        job_queue.run_daily(send_yearly_top_post_job, time=time(0, 0, tzinfo=cls.LOCAL_TIME), name="yearly_top_post")

        job_queue.run_repeating(
            callback=FollowUserScheduler.run,
            interval=300,
            first=10,
            name="followed_user_post_check",
            chat_id=chat_id
        )
