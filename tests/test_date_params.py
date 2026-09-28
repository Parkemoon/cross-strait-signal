"""Date-window query params on the public military and diplomacy reads are
typed as dates, so a malformed value is a 422 from FastAPI rather than a
500 from date.fromisoformat inside the handler."""
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from api.routes import diplomacy, military  # noqa: E402


@pytest.fixture(scope="module")
def client():
    app = FastAPI()
    app.include_router(military.router)
    app.include_router(diplomacy.router)
    return TestClient(app)


@pytest.mark.parametrize("path", [
    "/api/military/incursions?end=garbage",
    "/api/military/incursions?start=2026-13-40",
    "/api/military/exercises?end=x",
    "/api/diplomacy/statements?start=x",
])
def test_bad_date_is_422(client, path):
    assert client.get(path).status_code == 422
