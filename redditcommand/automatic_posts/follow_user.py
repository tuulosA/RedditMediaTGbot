# follow_user.py

import logging
import time
import os
from urllib.parse import urlparse

import aiohttp

from redditcommand.config import RedditClientManager
from redditcommand.handle_direct_link import handle_direct_link

from redditcommand.utils.filter_utils import FilterUtils
from redditcommand.utils.media_utils import MediaUtils, MediaDownloader, MediaSender
from redditcommand.utils.tempfile_utils import TempFileManager
from redditcommand.utils.file_state_utils import FollowedUserStore

logger = logging.getLogger(__name__)


async def check_and_send_new_user_posts(target):
    reddit = await RedditClientManager.get_client()
    followed_map = FollowedUserStore.load_user_follower_map()
    seen_post_ids = FollowedUserStore.load_seen_post_ids()
    new_seen = set(seen_post_ids)

    now = time.time()
    POST_AGE_THRESHOLD_SECONDS = 600  # Only consider posts from the last 10 minutes

    async with aiohttp.ClientSession() as session:
        for reddit_user, telegram_users in followed_map.items():
            try:
                redditor = await reddit.redditor(reddit_user)
                posts = [post async for post in redditor.submissions.new(limit=5)]

                for post in posts:
                    if post.id in seen_post_ids or post.id in new_seen:
                        continue
                    if (now - post.created_utc) > POST_AGE_THRESHOLD_SECONDS:
                        continue
                    if not FilterUtils.is_valid_url(post.url):
                        continue

                    await FilterUtils.attach_metadata(post)

                    # Handle gallery case separately
                    if hasattr(post, "is_gallery") and post.is_gallery and hasattr(post, "media_metadata"):
                        try:
                            top_item = post.gallery_data["items"][0]
                            media_id = top_item["media_id"]
                            media_info = post.media_metadata.get(media_id)
                            if media_info and "s" in media_info and "u" in media_info["s"]:
                                resolved_url = media_info["s"]["u"].replace("&amp;", "&")
                            else:
                                logger.warning(f"No valid media found in gallery post {post.id}")
                                continue
                        except Exception as e:
                            logger.error(f"Failed to resolve gallery for post {post.id}: {e}", exc_info=True)
                            continue
                    else:
                        resolved_url = await handle_direct_link(post.url, session, post)
                        if not resolved_url:
                            continue

                    # Download
                    if resolved_url.startswith("http://") or resolved_url.startswith("https://"):
                        temp_dir = TempFileManager.create_temp_dir("follow_")
                        filename = os.path.basename(urlparse(resolved_url).path) or f"{post.id}.media"
                        file_path = os.path.join(temp_dir, filename)
                        file_path = await MediaDownloader.download_file(resolved_url, file_path, session)
                    else:
                        file_path = resolved_url

                    if not file_path or not await MediaUtils.validate_file(file_path):
                        continue

                    # Filtering
                    post_text = f"{post.title} {getattr(post, 'selftext', '')}".lower()
                    for tg_user in telegram_users:
                        filters = FollowedUserStore.get_filters(tg_user)
                        if filters and not any(term in post_text for term in filters):
                            logger.info(f"Post {post.id} skipped for @{tg_user} due to filter mismatch.")
                            continue

                        # Caption & delivery
                        caption = f"New post by u/{reddit_user}!\n{post.title}"
                        if post.link_flair_text:
                            caption += f" [{post.link_flair_text}]"
                        if tg_user:
                            caption = f"@{tg_user}\n" + caption

                        await MediaSender.determine_type(file_path)(file_path, target, caption=caption)

                    new_seen.add(post.id)
                    FollowedUserStore.save_seen_post_ids(new_seen)

            except Exception as e:
                logger.error(f"Failed to process posts from u/{reddit_user}: {e}", exc_info=True)
