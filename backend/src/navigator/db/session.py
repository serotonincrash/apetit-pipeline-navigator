"""Database engine and sessions."""

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from navigator.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Generator[Session]:
    """A session that commits when the block succeeds and rolls back when it raises."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    with session_scope() as session:
        yield session
