import types
import pytest

pytestmark = pytest.mark.asyncio


# Minimal stand-in for asyncpraw.models.Submission
class DummySubmission:
    def __init__(self, id_, url):
        self.id = id_
        self.url = url


# Quiet the logger used by the module under test
@pytest.fixture(autouse=True)
def quiet_logger(monkeypatch):
    class L:
        def info(self, *a, **k): pass
        def warning(self, *a, **k): pass
        def error(self, *a, **k): pass
    monkeypatch.setattr(
        "redditcommand.utils.log_manager.LogManager.setup_main_logger",
        lambda: L()
    )


async def test_filter_empty_posts(monkeypatch):
    from redditcommand import filter_posts as FP
    f = FP.MediaPostFilter(subreddit_name="testsub", media_count=2)
    out = await f.filter([])
    assert out == []


async def test_filter_all_skipped_counts(monkeypatch):
    from redditcommand import filter_posts as FP
    from redditcommand.config import SkipReasons

    # Build a fake FilterUtils that always skips with different reasons
    calls = {"attach": 0, "log_skips_arg": None}

    reasons_cycle = [
        SkipReasons.NON_MEDIA,
        SkipReasons.BLACKLISTED,
        SkipReasons.PROCESSED,
        SkipReasons.GFYCAT,
        SkipReasons.WRONG_TYPE,
    ]

    class FU:
        idx = 0

        @staticmethod
        def should_skip(post, processed_urls, media_type):
            # rotate through reasons
            r = reasons_cycle[FU.idx % len(reasons_cycle)]
            FU.idx += 1
            return r

        @staticmethod
        async def attach_metadata(post):
            # should not be called when skipping
            calls["attach"] += 1

        @staticmethod
        def log_skips(skipped_dict):
            calls["log_skips_arg"] = skipped_dict

    # Patch the class reference used inside the module
    monkeypatch.setattr(FP, "FilterUtils", FU)

    posts = [DummySubmission(f"id{i}", f"https://x/{i}") for i in range(5)]
    f = FP.MediaPostFilter(subreddit_name="rtest", media_count=3)
    out = await f.filter(posts)

    # Everything skipped -> empty result, no attach calls
    assert out == []
    assert calls["attach"] == 0

    # log_skips should contain one count for each reason
    skipped = calls["log_skips_arg"]
    assert skipped[SkipReasons.NON_MEDIA] == 1
    assert skipped[SkipReasons.BLACKLISTED] == 1
    assert skipped[SkipReasons.PROCESSED] == 1
    assert skipped[SkipReasons.GFYCAT] == 1
    assert skipped[SkipReasons.WRONG_TYPE] == 1


async def test_filter_some_pass_and_sampling(monkeypatch):
    from redditcommand import filter_posts as FP

    # Deterministic sampling: return first N items
    monkeypatch.setattr(FP, "sample", lambda seq, n: list(seq)[:n])

    calls = {"attach_ids": []}

    class FU:
        @staticmethod
        def should_skip(post, processed_urls, media_type):
            return None  # keep all

        @staticmethod
        async def attach_metadata(post):
            calls["attach_ids"].append(post.id)

        @staticmethod
        def log_skips(skipped_dict):
            # all zeros expected
            pass

    monkeypatch.setattr(FP, "FilterUtils", FU)

    posts = [DummySubmission(str(i), f"https://x/{i}") for i in range(5)]
    f = FP.MediaPostFilter(subreddit_name="sub", media_count=2, processed_urls=set())
    out = await f.filter(posts)

    # First two chosen by our deterministic sampler
    assert [p.id for p in out] == ["0", "1"]
    # attach_metadata called for all candidates prior to sampling
    assert calls["attach_ids"] == ["0", "1", "2", "3", "4"]


async def test_filter_media_count_caps_to_available(monkeypatch):
    from redditcommand import filter_posts as FP

    # Deterministic sampling
    monkeypatch.setattr(FP, "sample", lambda seq, n: list(seq)[:n])

    class FU:
        @staticmethod
        def should_skip(post, processed_urls, media_type):
            return None

        @staticmethod
        async def attach_metadata(post):
            pass

        @staticmethod
        def log_skips(skipped_dict):
            pass

    monkeypatch.setattr(FP, "FilterUtils", FU)

    posts = [DummySubmission("a", "u/a"), DummySubmission("b", "u/b"), DummySubmission("c", "u/c")]
    f = FP.MediaPostFilter(subreddit_name="s", media_count=10)
    out = await f.filter(posts)
    assert len(out) == 3
    assert [p.id for p in out] == ["a", "b", "c"]


async def test_filter_passes_processed_urls_to_should_skip(monkeypatch):
    from redditcommand import filter_posts as FP

    seen = {"processed_urls_obj": None, "media_type": None}

    class FU:
        @staticmethod
        def should_skip(post, processed_urls, media_type):
            # capture the actual object passed in
            seen["processed_urls_obj"] = processed_urls
            seen["media_type"] = media_type
            return None

        @staticmethod
        async def attach_metadata(post):
            pass

        @staticmethod
        def log_skips(skipped_dict):
            pass

    monkeypatch.setattr(FP, "FilterUtils", FU)
    monkeypatch.setattr(FP, "sample", lambda seq, n: list(seq)[:n])

    processed = {"https://already/seen"}
    f = FP.MediaPostFilter(subreddit_name="s", media_type="video", media_count=1, processed_urls=processed)
    posts = [DummySubmission("x", "https://u/1")]
    out = await f.filter(posts)

    assert len(out) == 1
    # Ensure the same set instance is passed through
    assert seen["processed_urls_obj"] is processed
    assert seen["media_type"] == "video"
