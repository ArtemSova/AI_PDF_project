"""
Модуль конфигурации приложения.

Этот модуль определяет и валидирует все настройки приложения, загружаемые из переменных окружения.
Использует Pydantic для строгой типизации и валидации настроек. Настройки разделены по функциональным
группам: база данных, JWT, email, пути к файлам и AI модели.

Основной класс:
    Settings: Содержит все настройки приложения с валидацией и преобразованием типов

Особенности:
    - Автоматическая загрузка из .env файла
    - Валидация путей и создание директорий при необходимости
    - Динамическое формирование DATABASE_URL из отдельных параметров
    - Поддержка как локальных (Ollama), так и облачных (Mistral) AI моделей

Использование:
    from app.core.config import settings
    db_url = settings.DATABASE_URL
    secret_key = settings.JWT_SECRET

Зависимости:
    pydantic: BaseSettings для загрузки из окружения, Field для определения полей
    pydantic_settings: BaseSettings (если используется отдельная библиотека)
    pathlib.Path: Работа с путями файловой системы
"""

from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Основной класс настроек приложения AI_PDF.

    Настройки загружаются в следующем порядке приоритета:
    1. Переменные окружения системы
    2. .env файл в корне проекта
    3. Значения по умолчанию, указанные в классе

    Все строковые значения должны быть заданы, если не указано иное.
    """

    # Database
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    # Email
    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_HOST_USER: str
    EMAIL_HOST_PASSWORD: str
    EMAIL_USE_SSL: bool
    EMAIL_USE_STARTTLS: bool
    EMAIL_SENDER_NAME: str
    CONFIRM_BASE_URL: str
    RESET_BASE_URL: str

    # Путь сохранения файлов
    UPLOAD_ROOT: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "uploads",
        json_schema_extra={"env": "UPLOAD_ROOT"},   # `env`‑переменная теперь задаётся через json_schema_extra
    )

    # Ollama
    OLLAMA_BASE_URL: str
    OLLAMA_MODEL: str

    # Mistral
    MISTRAL_API_KEY: str
    MISTRAL_BASE_URL: str
    MISTRAL_MODEL: str

    # Оркестрация LLM
    USE_LANGGRAPH_FALLBACK: bool = True


    @property
    def DATABASE_URL(self) -> str:
        """
        Формирует строку подключения к PostgreSQL из отдельных параметров.

        Формат: postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}

        Возвращает:
            str: Полная строка подключения к базе данных
        """

        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


    @model_validator(mode="after")
    def _ensure_upload_dir(self) -> "Settings":  # Pydantic v2 требует self
        """
        Валидатор, который гарантирует существование директории для загрузок.

        Процесс:
            1. Получает путь из UPLOAD_ROOT
            2. Если путь относительный, преобразует его в абсолютный относительно корня проекта
            3. Создает директорию со всеми родительскими каталогами, если она не существует

        Возвращает:
            Settings: Объект настроек с валидированным путем

        Примечание:
            Вызывается автоматически Pydantic после загрузки всех полей.
        """

        upload_dir: Path = self.UPLOAD_ROOT

        # Если в переменной указан относительный путь – делаем его абсолютным.
        if not upload_dir.is_absolute():
            project_root = Path(__file__).resolve().parents[2]   # <корень проекта>
            upload_dir = project_root / upload_dir
            # Перезаписываем атрибут, чтобы дальше код использовал уже‑абсолютный путь.
            self.UPLOAD_ROOT = upload_dir

        # Физически создаём каталог, если его ещё нет.
        upload_dir.mkdir(parents=True, exist_ok=True)

        # При использовании @model_validator(mode="after") обязаны вернуть self.
        return self


    # Конфигурация для BaseSettings (чтение .env)
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

settings = Settings()
