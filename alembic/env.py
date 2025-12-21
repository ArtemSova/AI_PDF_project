"""
Модуль конфигурации Alembic для миграций базы данных.

Этот модуль настраивает Alembic для работы с асинхронным SQLAlchemy и PostgreSQL.
Определяет функции для выполнения миграций в онлайн и оффлайн режимах.

Основные компоненты:
    run_migrations_offline: Выполнение миграций без подключения к БД
    run_migrations_online: Асинхронное выполнение миграций с подключением к БД
    do_run_migrations: Вспомогательная функция для настройки контекста миграций

Процесс работы:
    1. Загрузка настроек из app.core.config.settings
    2. Построение DATABASE_URL из настроек
    3. Регистрация всех моделей SQLAlchemy через Base.metadata
    4. Определение режима выполнения (онлайн/оффлайн)
    5. Запуск соответствующих функций миграции

Особенности:
    Асинхронные операции с использованием create_async_engine
    Поддержка как онлайн, так и оффлайн миграций
    Автоматическое обнаружение моделей через Base.metadata
    Настройка пула соединений NullPool для миграций

Зависимости:
    alembic: Контекст миграций, конфигурация
    sqlalchemy: Движок, пул соединений
    sqlalchemy.ext.asyncio: Асинхронный движок
    asyncio: Асинхронное выполнение
    app.core.config: Настройки подключения к БД
    app.models: Все модели приложения для автогенерации
    app.db.session: Base класс с метаданными

Переменные окружения:
    Использует настройки из settings (загружаются из .env):
    - DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
"""

import sys
import os
import asyncio

from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

from app.core.config import settings

# Добавляем путь к проекту
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.models.user import User, Role, UserRole
from app.models.document import Document


from app.db.session import Base

DATABASE_URL = settings.DATABASE_URL

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata  # Base знает о всех моделях из импортов

def do_run_migrations(connection: Connection):
    """
    Вспомогательная функция для выполнения миграций.

    Аргументы:
        connection (Connection): Соединение с базой данных

    Процесс:
        1. Настройка Alembic контекста с переданным соединением
        2. Установка target_metadata для доступа к структуре моделей
        3. Запуск миграций внутри транзакции

    Примечание:
        Эта функция синхронная, используется внутри асинхронного контекста
        через connection.run_sync()
    """

    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_offline():
    """
    Выполняет миграции в оффлайн-режиме.

    Процесс:
        1. Конфигурация Alembic контекста с URL базы данных
        2. Установка target_metadata для автогенерации миграций
        3. Настройка literal_binds=True для безопасного рендеринга SQL
        4. Запуск миграций внутри транзакции

    Используется при:
        - Генерации миграционных скриптов (alembic revision --autogenerate)
        - Тестировании миграций без подключения к реальной БД

    Особенности:
        Не требует активного подключения к базе данных
        SQL генерируется как строки с параметрами
    """

    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    """
    Выполняет миграции в онлайн-режиме асинхронно.

    Процесс:
        1. Создание асинхронного движка SQLAlchemy с NullPool
        2. Установка асинхронного соединения с БД
        3. Запуск синхронной функции миграций в отдельном потоке
        4. Закрытие соединения и освобождение ресурсов

    Используется при:
        - Применении миграций к реальной базе данных (alembic upgrade head)
        - Проверке состояния миграций (alembic current)
        - Откате миграций (alembic downgrade)

    Особенности:
        Использует пул соединений NullPool для избежания конфликтов
        Асинхронное выполнение не блокирует event-loop
        Автоматическое управление соединением через async with
    """

    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())