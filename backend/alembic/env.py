"""Alembic environment.

Migrations run against a synchronous engine even though the application is
async. Migrations are a one-shot startup operation with no concurrency to gain
from, and the sync path is markedly simpler. Same driver, same URL.
"""

import logging

from sqlalchemy import create_engine, pool

from alembic import context
from app.config import get_settings
from app.db.tables import metadata

config = context.config

# Two lines in place of the ~28 the generated alembic.ini spends on logging.
# All we actually want is to see which revision is being applied.
logging.basicConfig(format="%(levelname)-5s [%(name)s] %(message)s")
logging.getLogger("alembic").setLevel(logging.INFO)

target_metadata = metadata


def _url() -> str:
    """Config wins when set, so tests can migrate their own database."""
    configured = config.get_main_option("sqlalchemy.url", None)
    return configured or get_settings().sqlalchemy_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
