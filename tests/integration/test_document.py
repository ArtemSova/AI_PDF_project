"""
Модуль интеграционных тестов для API документов.

Содержит end-to-end тесты для работы с документами в системе:
- Загрузка PDF документов через API
- Получение и обновление метаданных документов
- Проверка ролевого доступа (менеджер, руководитель)
- Тестирование изоляции данных между пользователями

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    tempfile: Создание временных файлов для тестирования
    os: Работа с файловой системой
    uuid: Генерация уникальных идентификаторов
    pathlib.Path: Работа с путями к файлам
    httpx.AsyncClient: Асинхронный HTTP клиент для взаимодействия с API
    sqlalchemy.ext.asyncio.AsyncSession: Асинхронная сессия для работы с БД
    app.models: Модели пользователей и ролей
    app.core.security: Функции безопасности для хеширования паролей
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
class TestDocumentsAPI:
    """Тесты для API эндпоинтов документов."""

    async def test_upload_and_get_document(self, client: AsyncClient, create_test_user):
        """
        Тестирует полный цикл работы с документом: загрузка, получение, обновление.

        Steps:
            1. Создание и аутентификация пользователя
            2. Генерация временного PDF файла
            3. Загрузка файла через API
            4. Проверка успешной загрузки
            5. Получение документа по ID
            6. Обновление метаданных документа

        Assertions:
            - Успешная загрузка файла
            - Наличие документа в списке пользователя
            - Возможность получения документа по ID
            - Успешное обновление метаданных документа

        Args:
            client: HTTP клиент для запросов к API.
            create_test_user: Фикстура, создающая тестового пользователя.
        """

        user = create_test_user
        login_data = {"username": user.email, "password": "SecurePassword123!"}
        login_response = await client.post("/auth/login", data=login_data)
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}

        # Создаем временный файл
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
            create_test_pdf_file(temp_file_path, "Тестовый документ для интеграции")

        try:
            with open(temp_file_path, 'rb') as f:
                file_content = f.read()

            # Загрузка документа
            response = await client.post(
                "/documents/upload_local",
                headers=headers,
                files={"file": (temp_file_path.name, file_content, "application/pdf")}
            )
            assert response.status_code == 200

            document_data = response.json()
            doc_id = document_data["id"]
            assert doc_id > 0

            # Получение списка документов
            response = await client.get("/documents/my_documents", headers=headers)
            assert response.status_code == 200
            docs_list = response.json()
            assert len(docs_list) >= 1
            assert any(doc["id"] == doc_id for doc in docs_list)

            # Получение конкретного документа
            response = await client.get(f"/documents/show_{doc_id}", headers=headers)
            assert response.status_code == 200
            retrieved_doc = response.json()
            assert retrieved_doc["id"] == doc_id
            assert retrieved_doc["user_id"] == user.id

            # Получение документа для редактирования
            response = await client.get(f"/documents/update_{doc_id}/edit", headers=headers)
            assert response.status_code == 200
            edit_doc = response.json()
            assert edit_doc["document_number"] == document_data["document_number"]

            # Обновление документа
            update_payload = {
                "document_number": "NEW-12345",
                "sender": "Updated Sender Inc."
            }
            response = await client.patch(f"/documents/update_{doc_id}", json=update_payload, headers=headers)
            assert response.status_code == 200
            updated_doc = response.json()
            assert updated_doc["document_number"] == "NEW-12345"
            assert updated_doc["sender"] == "Updated Sender Inc."

        finally:
            # Удаляем временный файл после теста
            if temp_file_path and temp_file_path.exists():
                os.unlink(temp_file_path)

    async def test_supervisor_access_to_documents(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует доступ руководителя к документам других пользователей.

        Steps:
            1. Создание пользователя с ролью 'manager' и загрузка документа
            2. Создание пользователя с ролью 'supervisor'
            3. Проверка доступа руководителя ко всем документам
            4. Проверка доступа руководителя к конкретному документу

        Assertions:
            - Руководитель видит документы, загруженные менеджером
            - В данных документа присутствует email загрузившего пользователя
            - Руководитель может получить конкретный документ по ID

        Args:
            client: HTTP клиент для запросов к API.
            db_session: Сессия БД для создания тестовых пользователей.
        """

        # Создаем пользователя-менеджера
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
        if not manager_role:
            manager_role = Role(name="manager")
            db_session.add(manager_role)
            await db_session.commit()
        manager_user_role = UserRole(user_id=manager_user.id, role_id=manager_role.id)
        db_session.add(manager_user_role)
        await db_session.commit()

        # Создаем пользователя-руководителя
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
        if not supervisor_role:
            supervisor_role = Role(name="supervisor")
            db_session.add(supervisor_role)
            await db_session.commit()
        supervisor_user_role = UserRole(user_id=supervisor_user.id, role_id=supervisor_role.id)
        db_session.add(supervisor_user_role)
        await db_session.commit()

        # Логин менеджера
        login_data = {"username": manager_email, "password": "ManagerPass123!"}
        login_response = await client.post("/auth/login", data=login_data)
        assert login_response.status_code == 200
        manager_token = login_response.json()["access_token"]
        manager_headers = {"Authorization": f"Bearer {manager_token}"}

        # Создаем и загружаем документ менеджером
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
            create_test_pdf_file(temp_file_path, "Тестовый документ для руководителя")

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

            # Логин руководителя
            login_data_sup = {"username": supervisor_email, "password": "SupervisorPass123!"}
            login_response_sup = await client.post("/auth/login", data=login_data_sup)
            assert login_response_sup.status_code == 200
            supervisor_token = login_response_sup.json()["access_token"]
            supervisor_headers = {"Authorization": f"Bearer {supervisor_token}"}

            # Руководитель получает все документы
            response = await client.get("/documents/supervisor/all_docs", headers=supervisor_headers)
            assert response.status_code == 200
            all_docs = response.json()
            # Должен увидеть документ, загруженный менеджером
            if doc_id:
                found_doc = next((doc for doc in all_docs if doc["id"] == doc_id), None)
                assert found_doc is not None
                assert found_doc["user_email"] == manager_email

            # Руководитель получает конкретный документ
            if doc_id:
                response = await client.get(f"/documents/supervisor/doc_{doc_id}", headers=supervisor_headers)
                assert response.status_code == 200
                specific_doc = response.json()
                assert specific_doc["id"] == doc_id
                assert specific_doc["user_email"] == manager_email

        finally:
            # Удаляем временный файл после теста
            if temp_file_path and temp_file_path.exists():
                os.unlink(temp_file_path)

    async def test_user_cannot_access_other_users_document(self, client: AsyncClient, db_session: AsyncSession):
        """
        Тестирует изоляцию данных между пользователями.

        Steps:
            1. Создание двух пользователей с ролью 'manager'
            2. Загрузка документа первым пользователем
            3. Попытка доступа к документу вторым пользователем
            4. Проверка, что доступ запрещен (404)

        Assertions:
            - Второй пользователь не может получить документ первого (404)
            - Второй пользователь не может обновить документ первого (404)
            - Первый пользователь сохраняет доступ к своему документу

        Args:
            client: HTTP клиент для запросов к API.
            db_session: Сессия БД для создания тестовых пользователей.
        """

        # Создаем первого пользователя
        user1_email = f"user1_{uuid.uuid4()}@example.com"
        user1_password_hash = get_password_hash("User1Pass123!")
        user1 = User(
            email=user1_email,
            password_hash=user1_password_hash,
            first_name="User",
            last_name="One",
            gender="male",
            is_active=True,
        )
        db_session.add(user1)
        await db_session.commit()
        await db_session.refresh(user1)

        role_result = await db_session.execute(select(Role).where(Role.name == "manager"))
        manager_role = role_result.scalar_one_or_none()
        if not manager_role:
            manager_role = Role(name="manager")
            db_session.add(manager_role)
            await db_session.commit()
        user1_role = UserRole(user_id=user1.id, role_id=manager_role.id)
        db_session.add(user1_role)
        await db_session.commit()

        # Создаем второго пользователя
        user2_email = f"user2_{uuid.uuid4()}@example.com"
        user2_password_hash = get_password_hash("User2Pass123!")
        user2 = User(
            email=user2_email,
            password_hash=user2_password_hash,
            first_name="User",
            last_name="Two",
            gender="female",
            is_active=True,
        )
        db_session.add(user2)
        await db_session.commit()
        await db_session.refresh(user2)

        user2_role = UserRole(user_id=user2.id, role_id=manager_role.id)
        db_session.add(user2_role)
        await db_session.commit()

        # Логин первого пользователя
        login_data1 = {"username": user1_email, "password": "User1Pass123!"}
        login_response1 = await client.post("/auth/login", data=login_data1)
        assert login_response1.status_code == 200
        token1 = login_response1.json()["access_token"]
        headers1 = {"Authorization": f"Bearer {token1}"}

        # Логин второго пользователя
        login_data2 = {"username": user2_email, "password": "User2Pass123!"}
        login_response2 = await client.post("/auth/login", data=login_data2)
        assert login_response2.status_code == 200
        token2 = login_response2.json()["access_token"]
        headers2 = {"Authorization": f"Bearer {token2}"}

        # Создаем и загружаем документ первым пользователем
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_file:
            temp_file_path = Path(tmp_file.name)
            create_test_pdf_file(temp_file_path, "Документ пользователя 1")

        try:
            with open(temp_file_path, 'rb') as f:
                file_content = f.read()

            upload_response = await client.post(
                "/documents/upload_local",
                headers=headers1,
                files={"file": (temp_file_path.name, file_content, "application/pdf")}
            )
            assert upload_response.status_code == 200

            doc_id = upload_response.json()["id"]
            assert doc_id > 0

            if doc_id:
                # Второй пользователь пытается получить документ первого
                response = await client.get(f"/documents/show_{doc_id}", headers=headers2)
                assert response.status_code == 404
                assert "Документ не найден или у вас нет прав на его просмотр" in response.json()["detail"]

                # Второй пользователь пытается обновить документ первого
                update_payload = {"sender": "Hacker Attempt"}
                response = await client.patch(f"/documents/update_{doc_id}", json=update_payload, headers=headers2)
                assert response.status_code == 404
                assert "Документ не найден или недостаточно прав для редактирования" in response.json()["detail"]

                # Первый пользователь всё ещё может получить свой документ
                response = await client.get(f"/documents/show_{doc_id}", headers=headers1)
                assert response.status_code == 200
                assert response.json()["id"] == doc_id

        finally:
            # Удаляем временный файл после теста
            if temp_file_path and temp_file_path.exists():
                os.unlink(temp_file_path)
