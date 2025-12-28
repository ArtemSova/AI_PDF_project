"""
Модуль тестирования Pydantic схем приложения.

Содержит юнит-тесты для валидации схем пользователей и документов.
Проверяет корректность работы валидаторов, обработку граничных случаев
и соответствие схем ожидаемому поведению API.

Классы тестов:
    TestUserSchemas: Тестирование схем для работы с пользователями
    TestDocumentSchemas: Тестирование схем для работы с документами

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    pydantic.ValidationError: Исключение для обработки ошибок валидации
    app.schemas.user: Схемы пользователей
    app.schemas.document: Схемы документов

Запуск файла:
    pytest tests\\unit\\test_schemas.py -v
"""

import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate, UserLogin, PasswordResetConfirm, PasswordChange, Gender
from app.schemas.document import DocumentUpdate


class TestUserSchemas:
    """
    Тесты для схем, связанных с пользователями.

    Включает тестирование:
        - Создания пользователя с корректными данными
        - Валидации паролей при регистрации
        - Входа пользователя в систему
        - Сброса и изменения пароля
        - Работы перечисления Gender
    """

    def test_user_create_valid(self):
        """
        Проверяет создание пользователя с валидными данными.

        Тест проверяет, что схема UserCreate корректно создается при
        передаче всех обязательных полей с правильными значениями,
        включая совпадающие пароли.

        Assertions:
            - Все поля пользователя корректно инициализируются
            - Email соответствует переданному значению
            - Пароль и подтверждение пароля совпадают
            - Имя, фамилия и пол установлены правильно
        """

        data = {
            "email": "test@example.com",
            "password": "password123",
            "password_confirm": "password123",
            "first_name": "John",
            "last_name": "Doe",
            "gender": "male"
        }
        user_create = UserCreate(**data)
        assert user_create.email == "test@example.com"
        assert user_create.password == "password123"
        assert user_create.first_name == "John"
        assert user_create.gender == "male"

    def test_user_create_password_mismatch(self):
        """
        Проверяет валидацию несовпадающих паролей при регистрации.

        Тест проверяет, что при создании пользователя с разными паролями
        в полях password и password_confirm выбрасывается исключение
        ValidationError.

        Raises:
            ValidationError: Должно быть выброшено при несовпадении паролей.
        """

        data = {
            "email": "test@example.com",
            "password": "password123",
            "password_confirm": "different_password",
            "first_name": "John",
            "last_name": "Doe",
            "gender": "male"
        }
        with pytest.raises(ValidationError):
            UserCreate(**data)

    def test_user_login_valid(self):
        """
        Проверяет создание схемы входа с валидными данными.

        Тест проверяет, что схема UserLogin корректно создается при
        передаче email и пароля.

        Assertions:
            - Email соответствует переданному значению
            - Пароль установлен правильно
        """

        data = {
            "email": "test@example.com",
            "password": "password123"
        }
        user_login = UserLogin(**data)
        assert user_login.email == "test@example.com"
        assert user_login.password == "password123"

    def test_password_reset_confirm_valid(self):
        """
        Проверяет подтверждение сброса пароля с валидными данными.

        Тест проверяет создание схемы PasswordResetConfirm при
        совпадающих новом пароле и его подтверждении.

        Assertions:
            - Токен сброса пароля установлен правильно
            - Новый пароль соответствует переданному значению
        """

        data = {
            "token": "some_token",
            "new_password": "newpassword123",
            "new_password_confirm": "newpassword123"
        }
        reset_confirm = PasswordResetConfirm(**data)
        assert reset_confirm.token == "some_token"
        assert reset_confirm.new_password == "newpassword123"

    def test_password_reset_confirm_password_mismatch(self):
        """
        Проверяет валидацию несовпадающих паролей при сбросе.

        Тест проверяет, что при подтверждении сброса пароля с разными
        значениями new_password и new_password_confirm выбрасывается
        исключение ValidationError.

        Raises:
            ValidationError: Должно быть выброшено при несовпадении паролей.
        """

        data = {
            "token": "some_token",
            "new_password": "newpassword123",
            "new_password_confirm": "different_new_password"
        }
        with pytest.raises(ValidationError):
            PasswordResetConfirm(**data)

    def test_password_change_valid(self):
        """
        Проверяет смену пароля с валидными данными.

        Тест проверяет создание схемы PasswordChange при
        совпадающих новом пароле и его подтверждении.

        Assertions:
            - Текущий пароль установлен правильно
            - Новый пароль соответствует переданному значению
        """

        data = {
            "current_password": "old_password",
            "new_password": "new_password123",
            "new_password_confirm": "new_password123"
        }
        pw_change = PasswordChange(**data)
        assert pw_change.current_password == "old_password"
        assert pw_change.new_password == "new_password123"

    def test_password_change_new_password_mismatch(self):
        """
        Проверяет валидацию несовпадающих паролей при смене пароля.

        Тест проверяет, что при смене пароля с разными значениями
        new_password и new_password_confirm выбрасывается исключение
        ValidationError.

        Raises:
            ValidationError: Должно быть выброшено при несовпадении паролей.
        """

        data = {
            "current_password": "old_password",
            "new_password": "new_password123",
            "new_password_confirm": "different_new_password"
        }
        with pytest.raises(ValidationError):
            PasswordChange(**data)

    def test_gender_enum(self):
        """
        Проверяет корректность работы перечисления Gender.

        Тест проверяет:
            - Значения элементов перечисления
            - Создание экземпляра перечисления из строки
            - Сравнение экземпляров перечисления

        Assertions:
            - Значения элементов соответствуют ожидаемым
            - Можно создать экземпляр перечисления по значению
            - Созданный экземпляр равен соответствующему элементу перечисления
        """
        assert Gender.male.value == "male"
        assert Gender.female.value == "female"
        # Проверим, что можно создать объект enum
        gender_male = Gender("male")
        assert gender_male == Gender.male


class TestDocumentSchemas:
    """
    Тесты для схем, связанных с документами.

    Включает тестирование:
        - Обновления документов с необязательными полями
        - Частичного обновления документов
    """

    def test_document_update_optional_fields(self):
        """
        Проверяет, что все поля в DocumentUpdate являются необязательными.

        Тест проверяет:
            - Создание пустого объекта обновления
            - Частичное обновление только некоторых полей
            - Корректную установку значений при частичном обновлении

        Assertions:
            - При создании пустого объекта все поля равны None
            - При частичном обновлении установленные поля имеют правильные значения
            - Не установленные поля остаются равными None
        """

        # Проверим, что все поля в DocumentUpdate опциональны
        update_data = DocumentUpdate()
        assert update_data.document_number is None
        assert update_data.amount is None

        # Проверим обновление отдельных полей
        partial_data = {"sender": "New Sender", "amount": 100.50}
        update_partial = DocumentUpdate(**partial_data)
        assert update_partial.sender == "New Sender"
        assert update_partial.amount == 100.50
        assert update_partial.document_number is None
        assert update_partial.purpose is None
