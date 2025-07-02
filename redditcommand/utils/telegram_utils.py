# redditcommand/utils/telegram_utils.py

from datetime import time, timezone, timedelta
from telegram.ext import Application, CommandHandler

from redditcommand.commands import RedditCommandHandler
from redditcommand.automatic_posts.top_post_scheduler import TopPostScheduler
from redditcommand.automatic_posts.follow_user import FollowUserScheduler


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

            'rtopday': TopPostScheduler.generate_command("TOP POST OF THE DAY", "day"),
            'rtopweek': TopPostScheduler.generate_command("TOP POST OF THE WEEK", "week"),
            'rtopmonth': TopPostScheduler.generate_command("TOP POST OF THE MONTH", "month"),
            'rtopyear': TopPostScheduler.generate_command("TOP POST OF THE YEAR", "year"),
            'rtopall': TopPostScheduler.generate_command("TOP POST OF ALL TIME", "all")
        }

        for cmd, handler in commands.items():
            application.add_handler(CommandHandler(cmd, handler))

    @classmethod
    def register_jobs(cls, application: Application, chat_id: int) -> None:
        job_queue = application.job_queue

        job_queue.run_daily(
            TopPostScheduler.generate_job("TOP POST OF THE DAY", "day"),
            time=time(17, tzinfo=cls.LOCAL_TIME),
            name="daily_top_post"
        )

        job_queue.run_daily(
            TopPostScheduler.generate_job("TOP POST OF THE WEEK", "week"),
            time=time(17, tzinfo=cls.LOCAL_TIME),
            days=(0,),
            name="weekly_top_post"
        )

        job_queue.run_daily(
            TopPostScheduler.generate_job("TOP POST OF THE MONTH", "month"),
            time=time(0, 0, tzinfo=cls.LOCAL_TIME),
            name="monthly_top_post"
        )

        job_queue.run_daily(
            TopPostScheduler.generate_job("TOP POST OF THE YEAR", "year"),
            time=time(0, 0, tzinfo=cls.LOCAL_TIME),
            name="yearly_top_post"
        )

        job_queue.run_repeating(
            callback=FollowUserScheduler.run,
            interval=300,
            first=10,
            name="followed_user_post_check",
            chat_id=chat_id
        )
