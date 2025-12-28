"""
Модуль общей конфигурации тестирования приложения.

Содержит фикстуры pytest для настройки тестовой среды:
- Изолированная in-memory SQLite база данных с автоматическим созданием схемы
- Предварительное заполнение таблицы ролей
- Фикстуры для работы с базой данных, HTTP-клиентом и мокированием email
- Вспомогательные функции для создания тестовых данных

Основные фикстуры:
    create_test_schema: Создает и инициализирует БД для каждого теста
    db_session: Предоставляет сессию для работы с БД
    client: HTTP-клиент для тестирования FastAPI эндпоинтов
    smtp_mock: Мок для сервиса отправки email
    create_test_user: Создает тестового пользователя с ролью manager

Вспомогательные функции:
    create_test_pdf_file: Создает PDF файл с тестовым содержимым для LLM анализа

Зависимости:
    pytest: Основной фреймворк для тестирования
    pytest-asyncio: Поддержка асинхронных тестов
    httpx: Асинхронный HTTP клиент
    sqlalchemy: ORM для работы с базой данных
    aiosqlite: Асинхронный драйвер для SQLite
    reportlab: Генерация PDF файлов для тестирования
    pydantic: Валидация данных (импортируется через зависимости приложения)
    fastapi: Веб-фреймворк (импортируется через приложение)
"""

import sys
import uuid
import pytest
import pytest_asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

from app.core.security import get_password_hash
from app.db.session import Base, get_db as original_get_db
from app.main import app as fastapi_app
from app.models.user import Role, User, UserRole

# 1 Убедиться, что корень проекта в sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# 2 Тестовый движок + фабрика сессий (sqlite in‑memory)
# engine создается внутри фикстуры, для корректного выхода из event loop
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

AsyncTestSession = sessionmaker(
    bind=None, # будет установлен позже, в фикстуре create_test_schema
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def create_test_schema():
    """
    Создает и инициализирует тестовую базу данных для каждого теста.

    Фикстура с scope="function" и autouse=True гарантирует, что для каждого
    теста создается чистая in-memory SQLite база данных с полной схемой
    и начальными данными. После завершения теста база уничтожается.

    Returns:
        AsyncEngine: Тестовый движок SQLAlchemy, привязанный к in-memory БД.

    Yields:
        AsyncEngine: Движок для работы с тестовой БД.

    Note:
        Автоматически заполняет таблицу ролей значениями:
        ["guest", "admin", "manager", "supervisor"]
    """
    # Создание движка для in-memory SQLite
    test_engine: AsyncEngine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        future=True,
    )

    # Обновление фабрики сессий с новым движком
    global AsyncTestSession
    AsyncTestSession = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Создание всех таблиц в БД
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Заполнение таблицы ролей начальными данными
    async with AsyncTestSession() as setup_session:
        roles_to_create = ["guest", "admin", "manager", "supervisor"]
        existing_roles = await setup_session.execute(select(Role).where(Role.name.in_(roles_to_create)))
        existing_names = {role.name for role in existing_roles.scalars().all()}

        roles_to_add = []
        for role_name in roles_to_create:
            if role_name not in existing_names:
                roles_to_add.append(Role(name=role_name))

        if roles_to_add:
            setup_session.add_all(roles_to_add)
            await setup_session.commit()

    yield test_engine

    # Очистка после теста
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(create_test_schema):
    """
    Предоставляет асинхронную сессию БД для теста.

    Args:
        create_test_schema: Фикстура, создающая тестовую схему БД.

    Returns:
        AsyncSession: Асинхронная сессия SQLAlchemy.

    Yields:
        AsyncSession: Сессия БД для использования в тестах.

    Note:
        Сессия автоматически закрывается после завершения теста.
        Не выполняет автоматический коммит или откат - управление
        транзакциями должно осуществляться в тестах или сервисах.
    """

    async with AsyncTestSession() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    """
    Предоставляет HTTP-клиент для тестирования FastAPI приложения.

    Args:
        db_session: Фикстура, предоставляющая тестовую сессию БД.

    Returns:
        AsyncClient: Асинхронный HTTP-клиент httpx.

    Yields:
        AsyncClient: Клиент, настроенный для тестирования эндпоинтов.

    Note:
        Временно переопределяет зависимость get_db в приложении FastAPI
        для использования тестовой сессии. Переопределение автоматически
        снимается после завершения теста.
    """

    from httpx import AsyncClient, ASGITransport

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Переопределение зависимости для использования тестовой сессии
        fastapi_app.dependency_overrides[original_get_db] = lambda: db_session
        yield ac

        # Очистка переопределений
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def smtp_mock(mocker):
    """
    Создает мок для сервиса отправки email.

    Args:
        mocker: Фикстура pytest-mock для создания моков.

    Returns:
        list: Список для хранения информации об отправленных письмах.

    Note:
        Каждое "отправленное" письмо добавляется в возвращаемый список
        в виде словаря с полями: to, subject, plain, html.
    """

    sent = []

    async def fake_send(msg, **kwargs):
        """Функция-заглушка для отправки email."""
        sent.append(
            {
                "to": msg["To"],
                "subject": msg["Subject"],
                "plain": msg.get_body(preferencelist=("plain",)).get_content(),
                "html": msg.get_body(preferencelist=("html",)).get_content(),
            }
        )
        return {}

    mocker.patch("app.core.email_sender._smtp_send", side_effect=fake_send)
    return sent

@pytest_asyncio.fixture
async def create_test_user(db_session: AsyncSession):
    """
    Фикстура для создания тестового пользователя с ролью 'manager'.

    Args:
        db_session: Асинхронная сессия базы данных.

    Returns:
        User: Созданный пользователь с установленной ролью manager.

    Note:
        Создает уникального пользователя для каждого теста с генерацией
        email через uuid. Пользователь активирован (is_active=True) и имеет
        хешированный пароль 'SecurePassword123!'.
        Если роль 'manager' не существует в БД, создает ее.
    """
    email = f"test_user_{uuid.uuid4()}@example.com"
    password_hash = get_password_hash("SecurePassword123!")
    user = User(
        email=email,
        password_hash=password_hash,
        first_name="Integration",
        last_name="Tester",
        gender="male",
        is_active=True,  # Активный пользователь!!!
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Назначаем роль 'manager' для возможности загрузки документов
    role_result = await db_session.execute(select(Role).where(Role.name == "manager"))
    manager_role = role_result.scalar_one_or_none()
    if not manager_role:
        manager_role = Role(name="manager")
        db_session.add(manager_role)
        await db_session.commit()

    user_role = UserRole(user_id=user.id, role_id=manager_role.id)
    db_session.add(user_role)
    await db_session.commit()

    return user

def create_test_pdf_file(file_path: Path,
                         document_number: str = "INV-TEST-123",
                         document_date: str = "2024-10-29",
                         sender: str = "ООО Ромашка",
                         purpose: str = "Оплата за тестовые услуги по счету INV-TEST-123",
                         amount: str = "15000.50",
                         your_company: str = "ООО «Моя фирма»",
                         additional_text: str = "Дополнительная тестовая информация."):
    """
    Создает тестовый PDF файл с содержимым, которое может распознать LLM.

    Функция генерирует PDF документ с четко структурированными данными,
    которые могут быть распознаны системой анализа документов. Используется
    для тестирования загрузки и обработки документов.

    Args:
        file_path: Путь для сохранения PDF файла.
        document_number: Номер документа для тестирования.
        document_date: Дата документа в произвольном формате.
        sender: Название организации-отправителя.
        purpose: Описание назначения платежа.
        amount: Сумма платежа в строковом формате.
        your_company: Название вашей компании (для контекста, но не для извлечения).
        additional_text: Дополнительный текст для заполнения документа.

    Note:
        Формат текста в PDF имитирует реальные документы и содержит поля,
        которые система должна распознать: номер, дата, отправитель, назначение, сумма.
        Расположение текста оптимизировано для парсинга LLM.
    """

    c = canvas.Canvas(str(file_path), pagesize=letter)

    # Формирование текста документа с четкой структурой
    text_content = f"""
    --- Примерный текст документа ---
    Номер документа: {document_number}
    Дата документа: {document_date}
    Отправитель: {sender}
    Назначение платежа: {purpose}
    Сумма: {amount} RUB
    ---
    Информация о вашей компании: {your_company}
    {additional_text}
    -------------------------------
    """

    # Добавление текста на страницу с фиксированным интервалом
    y_position = 750
    for line in text_content.split('\n'):
        c.drawString(72, y_position, line.strip())
        y_position -= 15 # Интервал между строками

    c.save()
