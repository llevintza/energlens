from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

# pool_pre_ping: serverless Postgres (Neon free suspends after ~5 min idle)
# drops the server side of pooled connections while the app process stays alive,
# so without a liveness check the first request after an idle gap fails with
# ConnectionDoesNotExistError instead of transparently reconnecting.
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
