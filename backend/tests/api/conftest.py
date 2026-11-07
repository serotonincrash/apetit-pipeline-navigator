"""API tests run against the worktree's test database, named by TEST_DATABASE_URL.

The schema comes from the Alembic migrations once per session, and every table is emptied
before each test. Tests that read artifact rows also need object storage, and skip when it
is not reachable.
"""

import os
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, text

from alembic import command


class ApiTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    test_database_url: str = ""
    test_s3_bucket: str = "navigator-test"


# Point the app at the test database and bucket before anything reads its settings.
_test_settings = ApiTestSettings()
if _test_settings.test_database_url:
    os.environ["DATABASE_URL"] = _test_settings.test_database_url
os.environ["S3_BUCKET"] = _test_settings.test_s3_bucket

from navigator.api.main import app  # noqa: E402
from navigator.db import session as db_session  # noqa: E402
from navigator.db.models import Base  # noqa: E402
from navigator.settings import get_settings  # noqa: E402

BACKEND = Path(__file__).resolve().parents[2]
PERSONA = {"X-Persona": "data_specialist:A. Reviewer"}


@pytest.fixture(scope="session")
def database() -> Iterator[Engine]:
    url = _test_settings.test_database_url
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a test database to run the API tests.")
    database_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not database_name.endswith("_test"):
        pytest.fail(
            f"TEST_DATABASE_URL names {database_name}; the tests empty it, so it must end in _test."
        )
    get_settings.cache_clear()
    db_session.get_engine.cache_clear()
    db_session._session_factory.cache_clear()  # pyright: ignore[reportPrivateUsage]
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "head")
    yield db_session.get_engine()
    db_session.get_engine().dispose()


@pytest.fixture(autouse=True)
def empty_tables(database: Engine) -> None:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with database.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client(database: Engine) -> TestClient:
    return TestClient(app)


@pytest.fixture
def storage() -> str:
    """The test bucket, created if needed. Skips the test when object storage is down."""
    settings = get_settings()
    host, _, port = settings.s3_endpoint.partition(":")
    try:
        socket.create_connection((host, int(port or 443)), timeout=1).close()
    except OSError:
        pytest.skip(f"Object storage is not reachable at {settings.s3_endpoint} (S3_ENDPOINT).")
    from navigator.storage import objects

    objects.ensure_bucket(settings.s3_bucket)
    return settings.s3_bucket
