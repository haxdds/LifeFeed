import os
import tempfile

# Point the app at throwaway storage before any app module is imported.
_tmp = tempfile.mkdtemp(prefix="lifefeed-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["MEDIA_DIR"] = f"{_tmp}/media"
os.environ.pop("REDIS_URL", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.cache import cache  # noqa: E402
from app.db import Base, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    cache._data.clear()
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(client):
    def _make(username: str, password: str = "password123") -> dict:
        r = client.post("/api/auth/register", json={"username": username, "password": password})
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]
        return {"headers": {"Authorization": f"Bearer {token}"}, **r.json()["user"]}

    return _make
