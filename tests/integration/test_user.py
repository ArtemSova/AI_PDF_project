"""
Модуль интеграционных тестов для API пользователей.

Содержит end-to-end тесты для работы с профилем пользователя:
- Получение данных профиля текущего пользователя
- Обновление информации пользователя

Все тесты выполняются через HTTP-запросы к API с использованием асинхронного клиента
и проверяют корректность работы системы аутентификации и обновления данных.

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    pytest.mark.asyncio: Декоратор для асинхронных тестов
    httpx.AsyncClient: Асинхронный HTTP клиент для взаимодействия с API
    sqlalchemy.ext.asyncio.AsyncSession: Асинхронная сессия для работы с базой данных
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
class TestUsersAPI:
    """Тесты для API эндпоинтов пользователей."""

    async def test_get_current_user_profile(self, client: AsyncClient, create_test_user):
        """
        Тестирует получение профиля текущего пользователя.

        Steps:
            1. Создание тестового пользователя
            2. Аутентификация пользователя для получения JWT токена
            3. Запрос профиля пользователя с использованием токена
            4. Проверка соответствия данных в ответе данным пользователя

        Assertions:
            - Успешная аутентификация (код 200)
            - Получение профиля (код 200)
            - Корректность данных профиля (email, имя, фамилия, пол)

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
        response = await client.get("/users/my_info", headers=headers)
        assert response.status_code == 200

        profile_data = response.json()
        assert profile_data["email"] == user.email
        assert profile_data["first_name"] == user.first_name
        assert profile_data["last_name"] == user.last_name
        assert profile_data["gender"] == user.gender

    async def test_update_user_info(self, client: AsyncClient, create_test_user, db_session: AsyncSession):
        """
        Тестирует обновление информации пользователя.

        Steps:
            1. Создание и аутентификация пользователя
            2. Отправка PATCH запроса с новыми данными профиля
            3. Проверка успешного ответа от API
            4. Верификация изменений в базе данных

        Assertions:
            - Успешное обновление данных (код 200)
            - Корректность обновленных данных в ответе API
            - Сохранение изменений в базе данных

        Args:
            client: HTTP клиент для запросов к API.
            create_test_user: Фикстура, создающая тестового пользователя.
            db_session: Сессия БД для проверки сохраненных изменений.
        """

        user = create_test_user
        login_data = {"username": user.email, "password": "SecurePassword123!"}
        login_response = await client.post("/auth/login", data=login_data)
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        update_data = {
            "first_name": "UpdatedFirstName",
            "last_name": "UpdatedLastName",
            "gender": "female"
        }
        response = await client.patch("/users/change_info", json=update_data, headers=headers)
        assert response.status_code == 200

        updated_profile = response.json()
        assert updated_profile["first_name"] == "UpdatedFirstName"
        assert updated_profile["last_name"] == "UpdatedLastName"
        assert updated_profile["gender"] == "female"

        # Проверяем, что изменения сохранились в БД
        await db_session.refresh(user)
        assert user.first_name == "UpdatedFirstName"
        assert user.last_name == "UpdatedLastName"
        assert user.gender == "female"
