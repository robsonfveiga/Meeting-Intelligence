"""The async engine and how a transaction is obtained.

Callers own transactions: `async with transaction() as conn`. The functions in
the sibling modules take a connection and never open one themselves, so a node
that writes a meeting and its turns can make both atomic.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
        )
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncConnection]:
    """One unit of work. Commits on success, rolls back on any exception."""
    async with get_engine().begin() as conn:
        yield conn
