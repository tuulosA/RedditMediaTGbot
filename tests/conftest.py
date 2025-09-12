# tests/conftest.py
import sys
from pathlib import Path
import dotenv
import pytest

@pytest.fixture(autouse=True)
def reset_global_session_singleton(monkeypatch):
    # Always clear the stored session so modules do not leak sessions across tests
    try:
        import redditcommand.utils.session as sess
        monkeypatch.setattr(sess.GlobalSession, "_session", None, raising=False)
    except Exception:
        pass

def pytest_configure():
    dotenv.load_dotenv = lambda *a, **k: None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
