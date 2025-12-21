"""
Модуль управления сессиями базы данных для асинхронного приложения.

Этот модуль настраивает и предоставляет компоненты для работы с базой данных:
- Базовый класс для SQLAlchemy моделей
- Асинхронный движок для подключения к PostgreSQL
- Фабрику асинхронных сессий
- Зависимость для внедрения сессий в эндпоинты FastAPI

Использует асинхронный драйвер asyncpg для эффективной работы с PostgreSQL
в асинхронном контексте FastAPI. Все операции с БД выполняются асинхронно.

Основные компоненты:
    Base: Базовый класс для всех SQLAlchemy ORM моделей
    engine: Асинхронный движок SQLAlchemy для управления соединениями
    AsyncSessionLocal: Фабрика для создания асинхронных сессий
    get_db: Dependency для FastAPI, предоставляющая сессию БД

Зависимости:
    sqlalchemy.ext.asyncio: AsyncSession, create_async_engine для асинхронной работы
    sqlalchemy.orm: sessionmaker, declarative_base для создания сессий и базового класса
    app.core.config: settings для получения параметров подключения к БД
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings


Base = declarative_base()
"""
Базовый класс для определения моделей SQLAlchemy.

Используется как родительский класс для всех ORM моделей приложения.
Автоматически регистрирует метаданные моделей для Alembic миграций.
Все модели должны наследоваться от этого класса.

Пример использования:
    class User(Base):
        __tablename__ = 'users'
        id = Column(Integer, primary_key=True)
        email = Column(String, unique=True, index=True)
"""

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)
"""
Асинхронный движок SQLAlchemy для управления подключениями к БД.

Аргументы:
    settings.DATABASE_URL (str): Строка подключения к PostgreSQL в формате
        postgresql+asyncpg://user:password@host:port/dbname
    echo (bool): Логирование SQL запросов (False для продакшена)
    future (bool): Использовать future-совместимое API SQLAlchemy

Особенности:
    - Использует асинхронный драйвер asyncpg для PostgreSQL
    - Управляет пулом соединений для эффективного использования ресурсов
    - Поддерживает асинхронные операции ввода-вывода
"""


AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
"""
Фабрика для создания асинхронных сессий базы данных.

Аргументы:
    bind (Engine): Движок, к которому привязываются сессии
    class_ (AsyncSession): Класс, который будет использоваться для создания сессий
    expire_on_commit (bool): Отключает автоматическое истечение объектов после коммита

Особенности:
    - Создает сессии, которые можно использовать в async/await контексте
    - Отключение expire_on_commit позволяет использовать объекты после коммита
      без необходимости их обновления
"""


async def get_db() -> AsyncSession:
    """
    Dependency для FastAPI, предоставляющая сессию базы данных.

    Процесс:
        1. Создание новой асинхронной сессии через AsyncSessionLocal
        2. Предоставление сессии в контексте асинхронного менеджера
        3. Автоматическое закрытие сессии после завершения запроса

    Возвращает:
        AsyncSession: Асинхронная сессия базы данных

    Использование в FastAPI:
        @app.get("/items/")
        async def read_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()

    Особенности:
        - Использует async with для гарантированного закрытия сессии
        - Одна сессия на HTTP запрос (паттерн "сессия на запрос")
        - Интегрируется с системой зависимостей FastAPI
        - Поддерживает транзакционный контекст
    """

    async with AsyncSessionLocal() as session:
        yield session
