import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

class Settings(BaseSettings):
    """
    Класс конфигурации приложения.
    Автоматически считывает переменные из файла .env в корне проекта.
    """
    BOT_TOKEN: str = "YOUR_BOT_TOKEN_HERE"
    GEMINI_API_KEY: str = "YOUR_GEMINI_API_KEY_HERE"
    DATABASE_URL: str = "sqlite+aiosqlite:///./dimup.db"
    ADMIN_TELEGRAM_ID: int = 0
    WEBAPP_URL: str = "http://localhost:8000/webapp"
    
    # Режим отладки
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
