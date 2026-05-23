from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# statement_cache_size=0 required for Supabase Supavisor (transaction pooler)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={"ssl": "require", "statement_cache_size": 0},
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
