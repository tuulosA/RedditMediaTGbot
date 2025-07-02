# redditcommand/automatic_posts/follow_user.py

import logging
import time
import os
from urllib.parse import urlparse
import aiohttp

from redditcommand.config import RedditClientManager, FollowUserConfig
from redditcommand.utils.filter_utils import FilterUtils
from redditcommand.utils.media_utils import MediaUtils, MediaDownloader, MediaSender
from redditcommand.utils.tempfile_utils import TempFileManager
from redditcommand.utils.file_state_utils import FollowedUserStore
from redditcommand.handle_direct_link import MediaLinkResolver

logger = logging.getLogger(__name__)


class FollowUserScheduler:
    @staticmethod
    async def run(context):
        target = context.job.chat_id
        monitor = FollowedUserMonitor()
        await monitor.check_and_send_all(target)


class FollowedUserMonitor:
    def __init__(self):
        self.reddit = None
        self.followed_map = FollowedUserStore.load_user_follower_map()
        self.seen_post_ids = FollowedUserStore.load_seen_post_ids()
        self.new_seen = set(self.seen_post_ids)

    async def check_and_send_all(self, target):
        self.reddit = await RedditClientManager.get_client()
        async with aiohttp.ClientSession() as session:
            resolver = MediaLinkResolver(session)
            for reddit_user, telegram_users in self.followed_map.items():
                await self._handle_user_posts(reddit_user, telegram_users, session, resolver, target)
        FollowedUserStore.save_seen_post_ids(self.new_seen)

    async def _handle_user_posts(self, reddit_user, telegram_users, session, resolver, target):
        try:
            redditor = await self.reddit.redditor(reddit_user)
            posts = [post async for post in redditor.submissions.new(limit=5)]
            now = time.time()

            for post in posts:
                if post.id in self.seen_post_ids or post.id in self.new_seen:
                    continue
                if (now - post.created_utc) > FollowUserConfig.POST_AGE_THRESHOLD_SECONDS:
                    continue
                if not FilterUtils.is_valid_url(post.url):
                    continue

                await FilterUtils.attach_metadata(post)

                resolved_url = await self._resolve_media(post, session, resolver)
                if not resolved_url:
                    continue

                file_path = await self._download_and_validate_media(post, resolved_url, session)
                if not file_path:
                    continue

                post_text = f"{post.title} {getattr(post, 'selftext', '')}".lower()
                for tg_user in telegram_users:
                    if self._should_skip_post(tg_user, post_text):
                        logger.info(f"Post {post.id} skipped for @{tg_user} due to filter mismatch.")
                        continue

                    caption = self._build_caption(tg_user, reddit_user, post)
                    await MediaSender.determine_type(file_path)(file_path, target, caption=caption)

                self.new_seen.add(post.id)

        except Exception as e:
            logger.error(f"Failed to process posts from u/{reddit_user}: {e}", exc_info=True)

    async def _resolve_media(self, post, session, resolver: MediaLinkResolver):
        if getattr(post, "is_gallery", False) and hasattr(post, "media_metadata"):
            try:
                top_item = post.gallery_data["items"][0]
                media_id = top_item["media_id"]
                media_info = post.media_metadata.get(media_id)
                if media_info and "s" in media_info and "u" in media_info["s"]:
                    return media_info["s"]["u"].replace("&amp;", "&")
                else:
                    logger.warning(f"No valid media found in gallery post {post.id}")
            except Exception as e:
                logger.error(f"Failed to resolve gallery for post {post.id}: {e}", exc_info=True)
        else:
            return await resolver.resolve(post.url, post)
        return None

    async def _download_and_validate_media(self, post, resolved_url, session):
        if resolved_url.startswith("http://") or resolved_url.startswith("https://"):
            temp_dir = TempFileManager.create_temp_dir("follow_")
            filename = os.path.basename(urlparse(resolved_url).path) or f"{post.id}.media"
            file_path = os.path.join(temp_dir, filename)
            file_path = await MediaDownloader.download_file(resolved_url, file_path, session)
        else:
            file_path = resolved_url

        if not file_path or not await MediaUtils.validate_file(file_path):
            return None
        return file_path

    def _should_skip_post(self, tg_user, post_text):
        filters = FollowedUserStore.get_filters(tg_user)
        return filters and not any(term in post_text for term in filters)

    def _build_caption(self, tg_user, reddit_user, post):
        caption = f"New post by u/{reddit_user}!\n{post.title}"
        if post.link_flair_text:
            caption += f" [{post.link_flair_text}]"
        if tg_user:
            caption = f"@{tg_user}\n" + caption
        return caption
