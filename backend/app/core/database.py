import logging
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create Async engine with pooler settings compatible with Supabase Pgbouncer
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# Async session factory
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Shared base class for SQLAlchemy models
Base = declarative_base()


async def get_db():
    """Yields a database session context and handles automatic session cleanup."""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
