import os
import tempfile
from pathlib import Path

test_database = tempfile.TemporaryDirectory(prefix="evidence-tests-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{Path(test_database.name) / 'test.db'}",
    APP_ACCESS_KEY="test-secret",
    REQUIRE_ACCESS_KEY="1",
    LLM_PROVIDER="ollama",
)
import pytest
from fastapi.testclient import TestClient

from desk.db import Base, engine
from desk.main import app
from desk.provider import Provider


@pytest.fixture(autouse=True)
def database(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(Provider, "check", lambda self: None)
    monkeypatch.setattr("desk.main.execute_run", lambda run_id: None)


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.headers["X-Access-Key"] = "test-secret"
        yield c
