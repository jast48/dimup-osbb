import urllib.parse
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Формируем корректный асинхронный URL для SQLAlchemy и Neon
db_url = settings.DATABASE_URL
connect_args = {}

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

if "asyncpg" in db_url:
    parsed = urllib.parse.urlparse(db_url)
    query_params = urllib.parse.parse_qs(parsed.query)
    has_ssl = "sslmode" in query_params or "ssl" in query_params or "neon.tech" in db_url
    query_params.pop("sslmode", None)
    query_params.pop("ssl", None)
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    db_url = urllib.parse.urlunparse(parsed._replace(query=new_query))
    if has_ssl:
        connect_args["ssl"] = True

# Создаем асинхронный движок SQLAlchemy
engine = create_async_engine(
    db_url,
    connect_args=connect_args,
    echo=settings.DEBUG,
)

# Фабрика асинхронных сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    """Базовый класс для всех моделей базы данных"""
    pass

async def get_db() -> AsyncSession:
    """Генератор сессий"""
    async with async_session_maker() as session:
        yield session
