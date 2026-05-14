import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Default: SQLite for local dev (zero dependencies)
# For production set DATABASE_URL=postgresql+asyncpg://...
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./chiya_saathi.db"
)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(DATABASE_URL, echo=False, connect_args=connect_args)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
