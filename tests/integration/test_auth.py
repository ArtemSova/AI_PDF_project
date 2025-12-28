"""
Модуль интеграционных тестов для системы аутентификации.

Содержит end-to-end тесты полного цикла аутентификации пользователей.
Проверяет корректность работы API эндпоинтов регистрации, логина и активации
учетных записей. Тесты взаимодействуют с реальной базой данных через фикстуры.

Тестовые сценарии:
    test_full_auth_flow: Полный цикл регистрации, активации и входа пользователя
    test_login_invalid_credentials: Проверка обработки неверных учетных данных

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    pytest.mark.asyncio: Поддержка асинхронных тестов
    httpx.AsyncClient: Асинхронный HTTP клиент для запросов к API
    sqlalchemy.ext.asyncio.AsyncSession: Асинхронная сессия для работы с БД
    app.models.user: Модель пользователя для проверки состояния в БД
    uuid: Генерация уникальных идентификаторов для тестовых данных
"""

import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_full_auth_flow(client: AsyncClient, db_session: AsyncSession):
    """
    Тестирует полный цикл аутентификации пользователя.

    Тест проверяет последовательность:
        1. Успешную регистрацию нового пользователя
        2. Блокировку входа для неактивированного пользователя (403)
        3. Активацию пользователя через прямое обновление в БД
        4. Успешный вход и получение JWT токена

    Args:
        client: Фикстура HTTP клиента для отправки запросов к API
        db_session: Фикстура асинхронной сессии БД для проверки и изменения состояния

    Assertions:
        - Регистрация возвращает код 200 и сообщение об успехе
        - Попытка входа неактивированного пользователя возвращает 403
        - После активации вход возвращает код 200 и JWT токен
        - Пользователь корректно сохраняется в базе данных

    Note:
        Используется уникальный email для каждого запуска теста через uuid,
        чтобы избежать конфликтов при параллельном выполнении тестов.
    """

    # Регистрация
    registration_data = {
        "email": f"integration_test_{uuid.uuid4()}@example.com", # Уникальный email для каждого запуска
        "password": "SecurePassword123!",
        "password_confirm": "SecurePassword123!",
        "first_name": "Integration",
        "last_name": "Tester",
        "gender": "male"
    }

    response = await client.post("/auth/register", json=registration_data)

    assert response.status_code == 200
    reg_result = response.json()
    assert "message" in reg_result or "detail" in reg_result # Проверяем наличие ключа
    if "message" in reg_result:
        assert reg_result["message"] == "Регистрация успешна. Проверьте почту для подтверждения."
    elif "detail" in reg_result:
        assert reg_result["detail"] == "Пользователь успешно зарегистрирован. Пожалуйста, подтвердите свой email."

    # Попытка логина (ожидаем 403)
    login_data = {
        "username": registration_data["email"], # Используем email как username
        "password": registration_data["password"]
    }
    response = await client.post("/auth/login", data=login_data)

    assert response.status_code == 403 # Пользователь неактивен
    assert "Учётная запись не активирована" in response.json()["detail"]

    # Эмуляция подтверждения email
    # Найдём пользователя в БД и установим is_active=True
    result = await db_session.execute(
        select(User).where(User.email == registration_data["email"])
    )
    user = result.scalar_one_or_none()
    assert user is not None
    user.is_active = True
    await db_session.commit()

    # Успешный логин
    response = await client.post("/auth/login", data=login_data)
    assert response.status_code == 200
    login_result = response.json()
    assert "access_token" in login_result
    assert login_result["token_type"] == "bearer"
    token = login_result["access_token"]
    assert token != ""  # Токен не пустой



@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient): # <-- Убран параметр db
    """
    Тестирует обработку неверных учетных данных при входе в систему.

    Проверяет два сценария:
        1. Вход с правильным email, но неправильным паролем
        2. Вход с несуществующим email

    Args:
        client: Фикстура HTTP клиента для отправки запросов к API

    Assertions:
        - Оба сценария возвращают код ошибки 400 или 422
        - Сообщение об ошибке содержит информацию о неверных учетных данных

    Note:
        Тест предварительно регистрирует пользователя, чтобы проверить
        обработку неправильного пароля к существующему аккаунту.
    """

    # Регистрация
    reg_data = {
        "email": f"invalid_login_{uuid.uuid4()}@example.com",
        "password": "ValidPass123!",
        "password_confirm": "ValidPass123!",
        "first_name": "Invalid",
        "last_name": "Login",
        "gender": "female"
    }
    await client.post("/auth/register", json=reg_data)

    # Попробуем залогиниться с неправильным паролем
    login_data = {
        "username": reg_data["email"],
        "password": "WrongPassword123!",
    }
    response = await client.post("/auth/login", data=login_data)

    assert response.status_code == 400
    if response.status_code == 400:
        assert "Неверный email или пароль" in response.json()["detail"]
    elif response.status_code == 422:
        response_detail = response.json().get("detail")
        assert response_detail is not None

    # Попробуем залогиниться с неправильным email
    login_data_wrong_email = {
        "username": "nonexistent@example.com",
        "password": reg_data["password"],
    }
    response = await client.post("/auth/login", data=login_data_wrong_email)

    assert response.status_code in [400, 422]
    if response.status_code == 400:
        assert "Неверный email или пароль" in response.json()["detail"]
    elif response.status_code == 422:
        response_detail = response.json().get("detail")
        assert response_detail is not None
