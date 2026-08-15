from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# Создаем асинхронный движок SQLAlchemy для работы с базой данных
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG, # В режиме DEBUG выводит все SQL-запросы в консоль для удобной отладки
)

# Фабрика асинхронных сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    """
    Базовый класс для всех моделей базы данных.
    Каждая таблица будет наследоваться от него.
    """
    pass

async def get_db() -> AsyncSession:
    """
    Генератор сессий для зависимостей FastAPI и хендлеров бота.
    Гарантирует автоматическое закрытие сессии после выполнения запроса.
    """
    async with async_session_maker() as session:
        yield session
