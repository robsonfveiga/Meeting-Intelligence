"""Integration test setup.

**Integration tests get their own database.** They previously shared the
development one, so every run ingested meetings into the corpus the evaluation
harness measures — and retrieval numbers moved between runs without the system
changing. Measurements that drift for reasons unrelated to the code are worse
than none, because tuning decisions get made on them.

Everything here is scoped to this package, so unit tests still need nothing
running.
"""

import os
from collections.abc import AsyncIterator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient

_DEV_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/meetings")
_TEST_DB = "meetings_test"
_TEST_URL = _DEV_URL.rsplit("/", 1)[0] + f"/{_TEST_DB}"

# Set before the application is imported, so its cached settings resolve to the
# test database rather than the development one.
os.environ["DATABASE_URL"] = _TEST_URL

# Extraction off by default here. It is the one ingest node that makes a
# completion call per window, so leaving it on would put a provider round trip —
# and a non-deterministic result — inside every test that uploads a file, none
# of which are about extraction. `test_facts.py` turns it back on against a
# stubbed provider, which is the only place the behaviour is actually asserted.
os.environ["EXTRACTION_ENABLED"] = "false"


def _create_test_database() -> None:
    admin_url = _DEV_URL.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (_TEST_DB,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{_TEST_DB}"')


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    from alembic.config import Config

    from alembic import command

    _create_test_database()
    config = Config("alembic.ini")
    # SQLAlchemy needs the driver named; the plain form defaults to psycopg2,
    # which is not installed.
    config.set_main_option(
        "sqlalchemy.url", _TEST_URL.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean_tables(database: None) -> None:
    """Each test starts from an empty corpus, so ordering never changes an outcome."""
    with psycopg.connect(_TEST_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE meetings CASCADE")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """A client with the real lifespan running, so the graph and checkpointer exist."""
    from asgi_lifespan import LifespanManager

    from app.main import app

    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client,
    ):
        yield async_client
