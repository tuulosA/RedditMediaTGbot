# redditcommand/utils/url_utils.py

from redditcommand.config import MediaValidationConfig

def is_valid_media_url(url: str) -> bool:
    url = url.lower()
    return (
        url.endswith(MediaValidationConfig.VALID_EXTENSIONS) or
        any(source in url for source in MediaValidationConfig.VALID_SOURCES)
    )

def matches_media_type(url: str, media_type: str) -> bool:
    url = url.lower()
    return (
        not media_type or
        (media_type == "image" and url.endswith(("jpg", "jpeg", "png"))) or
        (media_type == "video" and url.endswith(("mp4", "webm", "gifv", "gif"))) or
        ("streamable.com" in url and media_type == "video") or
        ("redgifs.com" in url and media_type == "video") or
        ("/gallery/" in url and media_type == "image") or
        ("v.redd.it" in url and media_type == "video")
    )
