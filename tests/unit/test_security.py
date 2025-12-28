"""
Модуль тестирования функций безопасности приложения.

Содержит юнит-тесты для хеширования паролей, создания и верификации JWT токенов.
Проверяет корректность работы криптографических функций, обработку исключений
и истечение срока действия токенов.

Классы тестов:
    TestSecurity: Тестирование функций модуля app.core.security

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    jose.jwt: Для создания и верификации JWT токенов
    datetime: Для работы с датами и временем
    app.core.security: Модуль с тестируемыми функциями безопасности
    app.core.config: Настройки приложения, включая секретные ключи
"""

from datetime import datetime, timedelta, timezone
from jose import jwt

from app.core.config import settings
from app.core.security import *


class TestSecurity:
    """
    Тесты для функций безопасности приложения.

    Включает тестирование:
        - Хеширования и проверки паролей
        - Создания и верификации регистрационных токенов
        - Создания и верификации аутентификационных токенов
        - Создания и верификации токенов сброса пароля
        - Обработки невалидных и просроченных токенов
    """

    def test_password_hashing(self):
        """
        Проверяет хеширование и верификацию паролей.

        Тест проверяет, что:
            - Хеш пароля отличается от исходного пароля
            - Валидный пароль проходит проверку
            - Неверный пароль не проходит проверку

        Assertions:
            - Хешированное значение не равно исходному паролю
            - verify_password возвращает True для корректного пароля
            - verify_password возвращает False для некорректного пароля
        """

        password = "test_password_123"
        hashed = get_password_hash(password)
        # Проверяем, что хэш отличается от пароля
        assert hashed != password
        # Проверяем, что пароль проходит проверку
        assert verify_password(password, hashed)
        # Проверяем, что другой пароль не проходит
        assert not verify_password("different_password", hashed)

    def test_create_and_verify_registration_token(self):
        """
        Проверяет создание и верификацию регистрационного токена.

        Тест проверяет, что регистрационный токен:
            - Содержит правильные данные (sub, email, type)
            - Корректно декодируется с использованием секретного ключа
            - Верифицируется функцией verify_token

        Note:
            Поле 'sub' в JWT всегда конвертируется в строку, даже если
            передано числовое значение.

        Assertions:
            - Декодированный payload содержит ожидаемые значения полей
            - Верифицированный payload совпадает с исходными данными
            - Тип токена установлен как 'registration'
        """

        data = {"sub": 123, "email": "test@example.com"}
        token = create_registration_token(data, expires_delta=timedelta(minutes=30))

        # Декодируем токен напрямую, чтобы проверить payload
        decoded_payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert decoded_payload["sub"] == "123" # sub всегда строка в токене
        assert decoded_payload["email"] == "test@example.com"
        assert decoded_payload["type"] == "registration"

        # Проверяем через verify_token
        verified_payload = verify_token(token)
        assert verified_payload["sub"] == "123"
        assert verified_payload["email"] == "test@example.com"
        assert verified_payload["type"] == "registration"

    def test_create_and_verify_auth_token(self):
        """
        Проверяет создание и верификацию аутентификационного токена.

        Тест проверяет, что аутентификационный токен (access token):
            - Содержит правильные данные (sub, type)
            - Корректно декодируется с использованием секретного ключа
            - Верифицируется функцией verify_token

        Assertions:
            - Декодированный payload содержит ожидаемое значение sub
            - Тип токена установлен как 'access'
            - Верифицированный payload совпадает с исходными данными
        """

        data = {"sub": 456}
        token = create_auth_token(data, expires_delta=timedelta(days=1))

        decoded_payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert decoded_payload["sub"] == "456"
        assert decoded_payload["type"] == "access"

        verified_payload = verify_token(token)
        assert verified_payload["sub"] == "456"
        assert verified_payload["type"] == "access"

    def test_create_and_verify_password_reset_token(self):
        """
        Проверяет создание и верификацию токена сброса пароля.

        Тест проверяет, что токен сброса пароля:
            - Содержит правильные данные (sub, email, type)
            - Корректно декодируется с использованием секретного ключа
            - Верифицируется функцией verify_token

        Assertions:
            - Декодированный payload содержит ожидаемые значения полей
            - Тип токена установлен как 'reset'
            - Верифицированный payload совпадает с исходными данными
        """

        data = {"sub": 789, "email": "reset@example.com"}
        token = create_password_reset_token(data, expires_delta=timedelta(minutes=15))

        decoded_payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert decoded_payload["sub"] == "789"
        assert decoded_payload["email"] == "reset@example.com"
        assert decoded_payload["type"] == "reset"

        verified_payload = verify_token(token)
        assert verified_payload["sub"] == "789"
        assert verified_payload["email"] == "reset@example.com"
        assert verified_payload["type"] == "reset"

    def test_verify_token_invalid(self):
        """
        Проверяет обработку невалидного токена.

        Тест проверяет, что функция verify_token:
            - Возвращает None при получении невалидной строки токена
            - Не выбрасывает исключение при некорректном формате токена

        Assertions:
            - Результат верификации невалидного токена равен None
        """

        invalid_token = "this.is.not.a.valid.token"
        result = verify_token(invalid_token)
        assert result is None

    def test_verify_token_expired(self, monkeypatch):
        """
        Проверяет обработку просроченного токена.

        Тест использует monkeypatch для изменения системного времени,
        чтобы создать токен с истекшим сроком действия.

        Args:
            monkeypatch: Фикстура pytest для временного изменения поведения

        Assertions:
            - Результат верификации просроченного токена равен None

        Note:
            Monkeypatch изменяет функцию datetime.now только в модуле
            app.core.security, чтобы токен был создан с истекшим сроком.
        """

        # Замораживаем время в прошлом
        fixed_time = datetime.now(timezone.utc) - timedelta(hours=1)
        monkeypatch.setattr("app.core.security.datetime", type("obj", (object,), {"now": lambda tz: fixed_time if tz == timezone.utc else datetime.now(tz)}))

        # Создаём токен, срок действия которого истёк 1 час назад
        data = {"sub": 999}
        expired_token = create_auth_token(data, expires_delta=timedelta(minutes=-30))

        result = verify_token(expired_token)
        assert result is None
