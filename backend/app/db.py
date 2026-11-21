from functools import lru_cache

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def get_database_url() -> URL:
    database_url = get_settings().database_url
    if database_url is None:
        raise RuntimeError("Укажите DATABASE_URL в файле .env.")

    try:
        url = make_url(database_url.get_secret_value())
    except (ArgumentError, ValueError):
        raise RuntimeError("В DATABASE_URL указана некорректная строка подключения.") from None

    if url.drivername in {"postgresql", "postgres"}:
        return url.set(drivername="postgresql+psycopg")
    if url.drivername != "postgresql+psycopg":
        raise RuntimeError("В DATABASE_URL укажите подключение PostgreSQL через psycopg.")
    return url


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(get_database_url(), pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)
