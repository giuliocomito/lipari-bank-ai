# Engine asincrono, fabbrica delle sessioni e sessione per ogni richiesta.
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,  # postgresql+asyncpg://...
    echo=settings.debug,  # con debug attivo, l'SQL generato finisce nel log
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
