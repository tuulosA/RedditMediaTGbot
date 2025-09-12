# tests/test_media_handler.py
import asyncio
import types
import pytest
from pathlib import Path

pytestmark = pytest.mark.asyncio

class DummyUpdate:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass

class DummySubmission:
    def __init__(self, id, url, title="t", flair=None):
        self.id = id
        self.url = url
        self.title = title
        self.link_flair_text = flair

# Autouse fixture to avoid opening real aiohttp sessions
@pytest.fixture(autouse=True)
def stub_global_session(monkeypatch):
    class DummySession:
        async def close(self): pass
    class GS:
        @staticmethod
        async def get():
            return DummySession()
    monkeypatch.setattr("redditcommand.utils.session.GlobalSession", GS)

# 1) Happy path
async def test_process_single_happy(monkeypatch, tmp_path):
    from redditcommand import media_handler as mh
    monkeypatch.setattr(mh, "Submission", DummySubmission)

    class CB:
        @staticmethod
        async def build(media, ic, iff, it): return "cap"
    monkeypatch.setattr("redditcommand.utils.media_utils.CaptionBuilder", CB)

    # Resolver returns local file
    resolved = tmp_path / "video.mp4"
    resolved.write_bytes(b"vid")
    class MLR:
        async def init(self): pass
        async def resolve(self, url, post=None): return str(resolved)
    monkeypatch.setattr("redditcommand.media_handler.MediaLinkResolver", MLR)

    # Async stubs for awaited funcs
    async def validate_file(p): return True
    async def validate_and_compress(p, m): return True
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.validate_file", staticmethod(validate_file))
    monkeypatch.setattr("redditcommand.utils.compressor.Compressor.validate_and_compress", staticmethod(validate_and_compress))

    async def download_file(url, out): return str(resolved)
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.download_file", staticmethod(download_file))

    async def handler(file_path, target, caption=None): return None
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaSender.determine_type", staticmethod(lambda p: handler))

    monkeypatch.setattr("redditcommand.utils.tempfile_utils.TempFileManager.cleanup_file", lambda *a, **k: None)

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    async with proc:
        post = DummySubmission("abc", "http://x/video.mp4")
        out = await proc.process_single(post, True, True, True)
        assert out is post

# 2) Missing URL
async def test_process_single_missing_url(monkeypatch):
    from redditcommand import media_handler as mh
    post = DummySubmission("id", url=None)
    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    out = await proc.process_single(post)
    assert out is None

# 3) Resolver returns None
async def test_process_single_resolve_none(monkeypatch):
    from redditcommand import media_handler as mh
    monkeypatch.setattr(mh, "Submission", DummySubmission)

    class CB:
        @staticmethod
        async def build(*a, **k): return "cap"
    monkeypatch.setattr("redditcommand.utils.media_utils.CaptionBuilder", CB)

    class MLR:
        async def init(self): pass
        async def resolve(self, url, post=None): return None
    monkeypatch.setattr("redditcommand.media_handler.MediaLinkResolver", MLR)

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    out = await proc.process_single(DummySubmission("x", "http://x/vid"), False, False, False)
    assert out is None

# 4) download_and_validate_media: too large -> cleanup and None
async def test_download_and_validate_media_too_large(monkeypatch, tmp_path):
    from redditcommand import media_handler as mh
    fp = tmp_path / "big.mp4"
    fp.write_bytes(b"big")

    async def fake_download(self, resolved_url, post_id):
        return str(fp)
    # Patch the method on the class in the media_handler module
    monkeypatch.setattr(mh.MediaProcessor, "download_file", fake_download, raising=False)

    async def validate_and_compress(p, m): return False
    monkeypatch.setattr("redditcommand.utils.compressor.Compressor.validate_and_compress",
                        staticmethod(validate_and_compress))

    cleaned = {"called": False}
    def cleanup(path): cleaned["called"] = True
    # Patch the symbol used by media_handler, not the utils module
    monkeypatch.setattr(mh, "TempFileManager",
                        types.SimpleNamespace(cleanup_file=cleanup))

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    out = await proc.download_and_validate_media("http://x/big.mp4", "p1")
    assert out is None
    assert cleaned["called"] is True

# 5) download_file: local paths
async def test_download_file_local_paths(monkeypatch, tmp_path):
    from redditcommand import media_handler as mh
    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())

    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")

    async def validate_file(p): return True
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.validate_file", staticmethod(validate_file))
    got = await proc.download_file(str(f), post_id="id1")
    assert got == str(f)

    async def validate_file_false(p): return False
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.validate_file", staticmethod(validate_file_false))
    got2 = await proc.download_file("C:\\nope\\file.mp4", post_id=None)
    assert got2 is None

# 6) download_file: http .gif conversion
async def test_download_file_http_gif(monkeypatch, tmp_path):
    from redditcommand import media_handler as mh
    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())

    td = tmp_path / "tmpdir"
    td.mkdir()
    monkeypatch.setattr("redditcommand.utils.tempfile_utils.TempFileManager.create_temp_dir", lambda prefix: str(td))
    monkeypatch.setattr("redditcommand.utils.tempfile_utils.TempFileManager.extract_post_id_from_url", lambda url: "pid")

    async def dl(url, out):
        p = Path(out)
        p.write_bytes(b"gif")
        gif_path = p.with_suffix(".gif")
        gif_path.write_bytes(b"gif")
        return str(gif_path)
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaDownloader.download_file", staticmethod(dl))

    async def convert_gif_to_mp4(p): return str(td / "out.mp4")
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.convert_gif_to_mp4", staticmethod(convert_gif_to_mp4))

    cleaned = {"count": 0}
    monkeypatch.setattr("redditcommand.utils.tempfile_utils.TempFileManager.cleanup_file", lambda p: cleaned.__setitem__("count", cleaned["count"] + 1))

    out = await proc.download_file("https://example.com/abc.gif", post_id=None)
    assert out == str(td / "out.mp4")
    assert cleaned["count"] == 1

# 7) upload_media: unsupported
async def test_upload_media_unsupported(monkeypatch):
    from redditcommand import media_handler as mh
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaSender.determine_type", staticmethod(lambda p: None))
    ok = await mh.MediaProcessor(reddit=object(), update=DummyUpdate()).upload_media("x.unknown", target=object(), caption=None)
    assert ok is False

# 8) upload_media: TimedOut returns True and cleans up
async def test_upload_media_timedout(monkeypatch):
    from telegram.error import TimedOut
    from redditcommand import media_handler as mh

    async def handler(file_path, target, caption=None):
        raise TimedOut("slow")

    monkeypatch.setattr("redditcommand.utils.media_utils.MediaSender.determine_type", staticmethod(lambda p: handler))
    cleaned = {"called": False}
    monkeypatch.setattr("redditcommand.utils.tempfile_utils.TempFileManager.cleanup_file", lambda p: cleaned.__setitem__("called", True))

    ok = await mh.MediaProcessor(reddit=object(), update=DummyUpdate()).upload_media("x.mp4", target=object(), caption=None)
    assert ok is True
    assert cleaned["called"] is True

# 9) process_batch filters non Submission
async def test_process_batch_filters_non_submission(monkeypatch):
    from redditcommand import media_handler as mh
    monkeypatch.setattr(mh, "Submission", DummySubmission)

    async def fake_single(self, obj, *a, **k):
        if isinstance(obj, DummySubmission):
            return obj
        return "not-a-submission"
    monkeypatch.setattr(mh.MediaProcessor, "process_single", fake_single, raising=False)

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    items = [DummySubmission("1", "u"), object()]
    out = await proc.process_batch(items, False, False, False)
    assert len(out) == 1 and isinstance(out[0], DummySubmission)

# 10) resolve_media_url: '/tmp' fast path with valid file
async def test_resolve_media_url_tmp_fast_path(monkeypatch, tmp_path):
    from redditcommand import media_handler as mh
    post_path = tmp_path / "ok.mp4"
    post_path.write_bytes(b"x")

    async def validate_file(p): return True
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.validate_file", staticmethod(validate_file))

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    post = DummySubmission("id", str(post_path))
    # Force url to start with /tmp to hit the branch
    post.url = "/tmp/" + post_path.name
    out = await proc.resolve_media_url(post)
    assert out == post.url

# 11) resolve_media_url: gallery branch
async def test_resolve_media_url_gallery(monkeypatch):
    from redditcommand import media_handler as mh
    async def resolve_gallery(gid, reddit): return "https://resolved/gallery.mp4"
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.resolve_reddit_gallery", staticmethod(resolve_gallery))

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    post = DummySubmission("id", "https://reddit.com/gallery/abc123")
    out = await proc.resolve_media_url(post)
    assert out == "https://resolved/gallery.mp4"

# 12) resolve_media_url: exception path returns None
async def test_resolve_media_url_exception(monkeypatch):
    from redditcommand import media_handler as mh
    class BadResolver:
        async def init(self): raise RuntimeError("boom")
        async def resolve(self, *a, **k): return "should not be called"
    monkeypatch.setattr("redditcommand.media_handler.MediaLinkResolver", BadResolver)

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    post = DummySubmission("id", "https://x/video.mp4")
    out = await proc.resolve_media_url(post)
    assert out is None

# 13) process_single: upload_media returns False, so overall returns None
async def test_process_single_upload_false(monkeypatch, tmp_path):
    from redditcommand import media_handler as mh
    monkeypatch.setattr(mh, "Submission", DummySubmission)

    class CB:
        @staticmethod
        async def build(*a, **k): return "cap"
    monkeypatch.setattr("redditcommand.utils.media_utils.CaptionBuilder", CB)

    # Resolve to local valid file
    f = tmp_path / "v.mp4"; f.write_bytes(b"x")
    class MLR:
        async def init(self): pass
        async def resolve(self, url, post=None): return str(f)
    monkeypatch.setattr("redditcommand.media_handler.MediaLinkResolver", MLR)

    async def validate_file(p): return True
    async def validate_and_compress(p, m): return True
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.validate_file", staticmethod(validate_file))
    monkeypatch.setattr("redditcommand.utils.compressor.Compressor.validate_and_compress", staticmethod(validate_and_compress))

    # Force upload_media to return False
    async def upload_false(self, file_path, target, caption): return False
    monkeypatch.setattr(mh.MediaProcessor, "upload_media", upload_false, raising=False)

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    out = await proc.process_single(DummySubmission("id", "http://x/vid.mp4"))
    assert out is None

# 14) upload_media: generic exception on all retries -> returns False and cleans up once at the end
async def test_upload_media_generic_exception(monkeypatch):
    from redditcommand import media_handler as mh
    calls = {"n": 0}
    async def handler(file_path, target, caption=None):
        calls["n"] += 1
        raise RuntimeError("nope")
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaSender.determine_type", staticmethod(lambda p: handler))

    cleaned = {"count": 0}
    def cleanup(p): cleaned["count"] += 1
    monkeypatch.setattr(mh, "TempFileManager",
                        types.SimpleNamespace(cleanup_file=cleanup))

    ok = await mh.MediaProcessor(reddit=object(), update=DummyUpdate()).upload_media("x.mp4", target=object(), caption=None)
    assert ok is False
    # Cleanup should still be called once after loop
    assert cleaned["count"] == 1
    # Retries executed
    from redditcommand.config import RetryConfig
    assert calls["n"] == RetryConfig.RETRY_ATTEMPTS

# 15) upload_media: fails then succeeds on second try
async def test_upload_media_succeeds_on_second_attempt(monkeypatch):
    from redditcommand import media_handler as mh
    stage = {"i": 0}
    async def handler(file_path, target, caption=None):
        stage["i"] += 1
        if stage["i"] == 1:
            raise RuntimeError("first try fails")
        return None
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaSender.determine_type", staticmethod(lambda p: handler))

    cleaned = {"count": 0}
    def cleanup(p): cleaned["count"] += 1
    monkeypatch.setattr(mh, "TempFileManager",
                        types.SimpleNamespace(cleanup_file=cleanup))

    ok = await mh.MediaProcessor(reddit=object(), update=DummyUpdate()).upload_media("x.mp4", target=object(), caption=None)
    assert ok is True
    # On success path, cleanup is called once inside the success branch
    assert cleaned["count"] == 1

# 16) download_file: non-http, non-existing, validate True returns the same path
async def test_download_file_non_http_validate_true(monkeypatch):
    from redditcommand import media_handler as mh
    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    async def validate_true(p): return True
    monkeypatch.setattr("redditcommand.utils.media_utils.MediaUtils.validate_file", staticmethod(validate_true))
    got = await proc.download_file("Z:\\imaginary\\foo.bar", post_id=None)
    assert got == "Z:\\imaginary\\foo.bar"

# 17) process_batch: one task raises, one returns Submission -> exception filtered out
async def test_process_batch_with_exception(monkeypatch):
    from redditcommand import media_handler as mh
    monkeypatch.setattr(mh, "Submission", DummySubmission)

    async def fake_single(self, obj, *a, **k):
        if isinstance(obj, DummySubmission):
            return obj
        raise RuntimeError("boom")
    monkeypatch.setattr(mh.MediaProcessor, "process_single", fake_single, raising=False)

    proc = mh.MediaProcessor(reddit=object(), update=DummyUpdate())
    items = [DummySubmission("ok", "u"), object()]
    out = await proc.process_batch(items, False, False, False)
    assert len(out) == 1 and isinstance(out[0], DummySubmission)
