"""
Модуль функциональных интеграционных тестов.

Содержит end-to-end тесты, проверяющие полные сценарии использования системы
с точки зрения конечного пользователя. Тесты фокусируются на бизнес-логике
и пользовательских сценариях, а не на технических деталях реализации.

Основные тестируемые сценарии:
    - Регистрация, подтверждение email и вход пользователя
    - Загрузка, просмотр и управление документами
    - Управление профилем пользователя
    - Ролевой доступ (менеджер, руководитель, гость)
    - Изоляция данных между пользователями

Философия тестирования:
    - Каждый тест представляет собой законченный пользовательский сценарий
    - Тесты независимы и самодостаточны
    - Проверяется ожидаемое поведение, а не внутренняя реализация
    - Используются реальные HTTP запросы и работа с базой данных

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    tempfile: Создание временных файлов для тестирования загрузки документов
    os: Работа с файловой системой для очистки временных файлов
    uuid: Генерация уникальных идентификаторов для изоляции тестов
    httpx.AsyncClient: Асинхронный HTTP клиент для взаимодействия с API
    sqlalchemy.ext.asyncio.AsyncSession: Асинхронная сессия для работы с БД
    sqlalchemy.select: Конструктор SQL запросов
    pathlib.Path: Объектно-ориентированная работа с путями файлов
    app.models.user: Модели пользователей, ролей и их связей
    app.core.security: Функции безопасности, включая хеширование паролей
    tests.conftest: Функция создания PDF документа
"""

import uuid
import tempfile
import os
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pathlib import Path

from app.models.user import User, UserRole, Role
from app.core.security import get_password_hash
from tests.conftest import create_test_pdf_file


@pytest.mark.asyncio
class TestAPIFunctionality:
    """
    Класс функциональных тестов, проверяющих полные пользовательские сценарии.

    Философия тестирования:
        - Тесты имитируют действия реального пользователя
        - Каждый тест проверяет законченный бизнес-сценарий
        - Предусловия, действия и ожидаемые результаты четко определены
        - Минимальная зависимость от внутренней реализации

    Особенности:
        - Все тесты используют уникальные данные для изоляции
        - Временные файлы корректно очищаются после тестов
        - Проверяется как успешные сценарии, так и обработка ошибок
    """

    async def test_user_registration_and_login_flow(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует полный сценарий регистрации и входа пользователя.

        Предусловие:
            - Нет пользователя с тестовым email в системе

        Шаги выполнения:
            1. Регистрация нового пользователя с валидными данными
            2. Проверка успешной регистрации и получения сообщения о подтверждении
            3. Эмуляция подтверждения email через прямое обновление в БД
            4. Вход в систему с подтвержденными учетными данными
            5. Получение JWT токена доступа

        Ожидаемые результаты:
            - Регистрация проходит успешно (код 200)
            - Пользователь получает сообщение о необходимости подтверждения email
            - До подтверждения email пользователь неактивен (is_active=False)
            - После подтверждения вход проходит успешно (код 200)
            - Полученный токен доступа валиден и не пустой

        Args:
            client: HTTP клиент для отправки запросов к API
            db_session: Сессия БД для проверки и изменения состояния пользователя
        """

        test_email = f"functional_test_{uuid.uuid4()}@example.com"
        password = "SecurePassword123!"

        registration_data = {
            "email": test_email,
            "password": password,
            "password_confirm": password,
            "first_name": "Functional",
            "last_name": "Tester",
            "gender": "female"
        }

        # Регистрация
        response = await client.post("/auth/register", json=registration_data)
        assert response.status_code == 200
        assert "message" in response.json()
        assert "Проверьте почту для подтверждения" in response.json()["message"]

        # Имитация подтверждения (вручную в БД)
        user_result = await db_session.execute(select(User).where(User.email == test_email))
        user = user_result.scalar_one_or_none()
        assert user is not None
        assert not user.is_active # Проверим, что пользователь неактивен до подтверждения

        user.is_active = True
        await db_session.commit()

        # Логин после подтверждения
        login_data = {"username": test_email, "password": password}
        response = await client.post("/auth/login", data=login_data)
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

        token = response.json()["access_token"]
        assert token != ""

    async def test_document_upload_and_retrieval_as_user(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует сценарий работы пользователя с документами.

        Предусловие:
            - Существует активный пользователь с ролью 'manager'

        Шаги выполнения:
            1. Создание тестового пользователя с ролью manager
            2. Аутентификация пользователя
            3. Создание временного PDF файла
            4. Загрузка файла через API
            5. Проверка наличия документа в списке пользователя
            6. Получение деталей загруженного документа

        Ожидаемые результаты:
            - Пользователь успешно аутентифицируется (код 200)
            - Документ загружается
            - Загруженный документ появляется в списке документов пользователя
            - Детали документа содержат корректные данные (ID, user_id)

        Args:
            client: HTTP клиент для отправки запросов к API
            db_session: Сессия БД для создания тестового пользователя
        Важно:
            Ollama должна быть запущена на сервере.
        """

        # Создание пользователя
        user_email = f"doc_tester_{uuid.uuid4()}@example.com"
        password_hash = get_password_hash("DocPass123!")
        user = User(
            email=user_email,
            password_hash=password_hash,
            first_name="Doc",
            last_name="Tester",
            gender="male",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        role_result = await db_session.execute(select(Role).where(Role.name == "manager"))
        manager_role = role_result.scalar_one_or_none()
        user_role = UserRole(user_id=user.id, role_id=manager_role.id)
        db_session.add(user_role)
        await db_session.commit()

        # Аутентификация
        login_data = {"username": user_email, "password": "DocPass123!"}
        login_response = await client.post("/auth/login", data=login_data)
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Загрузка документ
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
            create_test_pdf_file(temp_file_path, "Функциональный тест: документ пользователя")

        try:
            with open(temp_file_path, 'rb') as f:
                file_content = f.read()

            response = await client.post(
                "/documents/upload_local",
                headers=headers,
                files={"file": (temp_file_path.name, file_content, "application/pdf")}
            )

            assert response.status_code == 200


            document_data = response.json()
            doc_id = document_data["id"]
            assert doc_id > 0

            # Проверка списка документов
            response = await client.get("/documents/my_documents", headers=headers)
            assert response.status_code == 200
            docs_list = response.json()
            assert len(docs_list) >= 1
            assert any(doc["id"] == doc_id for doc in docs_list)

            # Проверка деталей конкретного документа
            response = await client.get(f"/documents/show_{doc_id}", headers=headers)
            assert response.status_code == 200
            retrieved_doc = response.json()
            assert retrieved_doc["id"] == doc_id
            assert retrieved_doc["user_id"] == user.id

        finally:
            if temp_file_path and temp_file_path.exists():
                os.unlink(temp_file_path)

    async def test_user_profile_management(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует сценарий управления профилем пользователя.

        Предусловие:
            - Существует активный пользователь

        Шаги выполнения:
            1. Создание тестового пользователя
            2. Аутентификация пользователя
            3. Получение текущего профиля
            4. Обновление профильных данных
            5. Повторное получение профиля для проверки изменений

        Ожидаемые результаты:
            - Пользователь может получить свой профиль (код 200)
            - Данные профиля соответствуют исходным данным
            - Обновление профиля проходит успешно (код 200)
            - Обновленные данные отображаются в ответе API
            - Изменения сохраняются в базе данных

        Args:
            client: HTTP клиент для отправки запросов к API
            db_session: Сессия БД для создания тестового пользователя
        """

        # Создание пользователя
        user_email = f"profile_test_{uuid.uuid4()}@example.com"
        password_hash = get_password_hash("ProfilePass123!")
        user = User(
            email=user_email,
            password_hash=password_hash,
            first_name="Original",
            last_name="User",
            gender="female",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Аутентификация
        login_data = {"username": user_email, "password": "ProfilePass123!"}
        login_response = await client.post("/auth/login", data=login_data)
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Получение профиля
        response = await client.get("/users/my_info", headers=headers)
        assert response.status_code == 200
        profile_data = response.json()
        assert profile_data["email"] == user_email
        assert profile_data["first_name"] == "Original"
        assert profile_data["last_name"] == "User"
        assert profile_data["gender"] == "female"

        # Изменение профиля
        update_data = {
            "first_name": "UpdatedFirstName",
            "last_name": "UpdatedLastName",
            "gender": "male"
        }
        response = await client.patch("/users/change_info", json=update_data, headers=headers)
        assert response.status_code == 200

        updated_profile = response.json()
        assert updated_profile["first_name"] == "UpdatedFirstName"
        assert updated_profile["last_name"] == "UpdatedLastName"
        assert updated_profile["gender"] == "male"

        # Повторное получение профиля для проверки изменений
        response = await client.get("/users/my_info", headers=headers)
        assert response.status_code == 200
        final_profile_data = response.json()
        assert final_profile_data["first_name"] == "UpdatedFirstName"
        assert final_profile_data["last_name"] == "UpdatedLastName"
        assert final_profile_data["gender"] == "male"

    async def test_supervisor_document_access(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует сценарий доступа руководителя к документам.

        Предусловие:
            - Существует пользователь-менеджер с загруженным документом
            - Существует пользователь-руководитель

        Шаги выполнения:
            1. Создание пользователя с ролью manager
            2. Создание пользователя с ролью supervisor
            3. Загрузка документа менеджером
            4. Вход руководителя в систему
            5. Получение списка всех документов руководителем
            6. Получение деталей конкретного документа руководителем

        Ожидаемые результаты:
            - Руководитель может получить список всех документов (код 200)
            - В списке присутствует документ, загруженный менеджером
            - В данных документа присутствует email менеджера
            - Руководитель может получить конкретный документ по ID (код 200)

        Args:
            client: HTTP клиент для отправки запросов к API
            db_session: Сессия БД для создания тестовых пользователей
        Важно:
            Ollama должна быть запущена на сервере.
        """

        # Создание менеджера
        manager_email = f"manager_{uuid.uuid4()}@example.com"
        manager_password_hash = get_password_hash("ManagerPass123!")
        manager_user = User(
            email=manager_email,
            password_hash=manager_password_hash,
            first_name="Manager",
            last_name="User",
            gender="female",
            is_active=True,
        )
        db_session.add(manager_user)
        await db_session.commit()
        await db_session.refresh(manager_user)

        role_result = await db_session.execute(select(Role).where(Role.name == "manager"))
        manager_role = role_result.scalar_one_or_none()
        manager_user_role = UserRole(user_id=manager_user.id, role_id=manager_role.id)
        db_session.add(manager_user_role)
        await db_session.commit()

        # Подготовка: Создание руководителя
        supervisor_email = f"supervisor_{uuid.uuid4()}@example.com"
        supervisor_password_hash = get_password_hash("SupervisorPass123!")
        supervisor_user = User(
            email=supervisor_email,
            password_hash=supervisor_password_hash,
            first_name="Supervisor",
            last_name="User",
            gender="male",
            is_active=True,
        )
        db_session.add(supervisor_user)
        await db_session.commit()
        await db_session.refresh(supervisor_user)

        role_result = await db_session.execute(select(Role).where(Role.name == "supervisor"))
        supervisor_role = role_result.scalar_one_or_none()
        supervisor_user_role = UserRole(user_id=supervisor_user.id, role_id=supervisor_role.id)
        db_session.add(supervisor_user_role)
        await db_session.commit()

        # Аутентификация менеджера и загрузка документа
        login_data_manager = {"username": manager_email, "password": "ManagerPass123!"}
        login_response_manager = await client.post("/auth/login", data=login_data_manager)
        assert login_response_manager.status_code == 200
        manager_token = login_response_manager.json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
            create_test_pdf_file(temp_file_path, "Документ для функционального теста руководителя")

        try:
            with open(temp_file_path, 'rb') as f:
                file_content = f.read()

            upload_response = await client.post(
                "/documents/upload_local",
                headers=manager_headers,
                files={"file": (temp_file_path.name, file_content, "application/pdf")}
            )
            assert upload_response.status_code == 200

            doc_id = upload_response.json()["id"]
            assert doc_id > 0

        finally:
            if temp_file_path and temp_file_path.exists():
                os.unlink(temp_file_path)

        # Аутентификация руководителя
        login_data_supervisor = {"username": supervisor_email, "password": "SupervisorPass123!"}
        login_response_supervisor = await client.post("/auth/login", data=login_data_supervisor)
        assert login_response_supervisor.status_code == 200
        supervisor_token = login_response_supervisor.json()["access_token"]
        supervisor_headers = {"Authorization": f"Bearer {supervisor_token}"}

        if doc_id:
            # Руководитель получает все документы
            response = await client.get("/documents/supervisor/all_docs", headers=supervisor_headers)
            assert response.status_code == 200
            all_docs = response.json()
            found_doc = next((doc for doc in all_docs if doc["id"] == doc_id), None)
            assert found_doc is not None
            assert found_doc["user_email"] == manager_email

            # Руководитель получает конкретный документ
            response = await client.get(f"/documents/supervisor/doc_{doc_id}", headers=supervisor_headers)
            assert response.status_code == 200
            specific_doc = response.json()
            assert specific_doc["id"] == doc_id
            assert specific_doc["user_email"] == manager_email

    async def test_forbidden_access_by_role(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует сценарий запрета доступа для пользователей без прав.

        Предусловие:
            - Существует пользователь с ролью 'guest'

        Шаги выполнения:
            1. Создание пользователя с ролью guest
            2. Аутентификация пользователя-гостя
            3. Попытка загрузки документа (запрещено для guest)
            4. Попытка доступа к эндпоинтам руководителя (запрещено для guest)

        Ожидаемые результаты:
            - Запросы к защищенным эндпоинтам возвращают код ошибки (403 или 404)
            - Пользователь с ролью guest не может выполнять действия,
              требующие более высоких привилегий

        Args:
            client: HTTP клиент для отправки запросов к API
            db_session: Сессия БД для создания тестового пользователя
        """

        # Создание пользователя-гостя
        guest_email = f"guest_{uuid.uuid4()}@example.com"
        guest_password_hash = get_password_hash("GuestPass123!")
        guest_user = User(
            email=guest_email,
            password_hash=guest_password_hash,
            first_name="Guest",
            last_name="User",
            gender="male",
            is_active=True,
        )
        db_session.add(guest_user)
        await db_session.commit()
        await db_session.refresh(guest_user)

        role_result = await db_session.execute(select(Role).where(Role.name == "guest"))
        guest_role = role_result.scalar_one_or_none()
        guest_user_role = UserRole(user_id=guest_user.id, role_id=guest_role.id)
        db_session.add(guest_user_role)
        await db_session.commit()

        # Аутентификация гостя
        login_data_guest = {"username": guest_email, "password": "GuestPass123!"}
        login_response_guest = await client.post("/auth/login", data=login_data_guest)
        assert login_response_guest.status_code == 200
        guest_token = login_response_guest.json()["access_token"]
        guest_headers = {"Authorization": f"Bearer {guest_token}"}

        # Попытка загрузки документа (должна быть запрещена для 'guest')
        # Создаём временный файл для загрузки
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
            create_test_pdf_file(temp_file_path, "Документ, который гость не должен загрузить")

        try:
            with open(temp_file_path, 'rb') as f:
                file_content = f.read()

            response = await client.post(
                "/documents/upload_local",
                headers=guest_headers,
                files={"file": (temp_file_path.name, file_content, "application/pdf")}
            )
            assert response.status_code == 403

        finally:
            if temp_file_path and temp_file_path.exists():
                os.unlink(temp_file_path)

        # Попытка доступа к эндпоинтам руководителя (должна быть запрещена для 'guest')
        response = await client.get("/documents/supervisor/all_docs", headers=guest_headers)
        assert response.status_code == 403
