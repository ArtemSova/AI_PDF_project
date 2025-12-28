"""
Модуль Pydantic схем для пользователей.

Этот модуль определяет структуры данных для валидации, сериализации и
документирования API эндпоинтов, связанных с пользователями. Все схемы наследуются
от BaseModel Pydantic и включают валидацию полей, таких как email и пароли.

Основные схемы:
    Gender: Перечисление для пола пользователя
    UserCreate: Для регистрации нового пользователя
    UserLogin: Для входа в систему
    UserResponse: Для ответа с данными пользователя
    ResendConfirmationRequest: Для повторной отправки подтверждения email
    PasswordResetRequest: Для запроса сброса пароля
    PasswordResetConfirm: Для подтверждения сброса пароля
    UserInfoUpdate: Для обновления профиля пользователя
    PasswordChange: Для смены пароля

Все схемы используют строгую валидацию: EmailStr для email, минимальную длину пароля,
проверку совпадения паролей через валидаторы.

Зависимости:
    pydantic: BaseModel, EmailStr, Field, field_validator, ConfigDict
    enum: Enum для перечислений
"""

from enum import Enum
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from pydantic_core.core_schema import ValidationInfo


class Gender(str, Enum):
    """
    Перечисление для представления пола пользователя.

    Используется для валидации поля gender в схемах пользователей.

    Values:
        male: Мужской пол
        female: Женский пол
    """

    male = "male"
    female = "female"


class UserCreate(BaseModel):
    """
    Схема для регистрации нового пользователя.

    Включает валидацию паролей на минимальную длину и совпадение.

    Attributes:
        email: Email пользователя с автоматической валидацией формата.
        password: Пароль длиной не менее 6 символов.
        password_confirm: Подтверждение пароля.
        first_name: Имя пользователя.
        last_name: Фамилия пользователя.
        gender: Пол пользователя, должен быть 'male' или 'female'.

    Raises:
        ValueError: Если password и password_confirm не совпадают.

    Example:
        ```json
        {
            "email": "user@example.com",
            "password": "securepass123",
            "password_confirm": "securepass123",
            "first_name": "Иван",
            "last_name": "Иванов",
            "gender": "male"
        }
        ```
    """

    email: EmailStr
    password: str = Field(min_length=6)
    password_confirm: str = Field(min_length=6)
    first_name: str
    last_name: str
    gender: str

    @field_validator("password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        """
        Проверяет совпадение пароля и его подтверждения.

        Args:
            v: Значение поля password_confirm.
            info: Контекст валидации с уже провалидированными данными.

        Returns:
            str: Значение password_confirm, если проверка пройдена.

        Raises:
            ValueError: Если пароли не совпадают.
        """
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Пароли не совпадают.")
        return v


class UserLogin(BaseModel):
    """
    Схема для входа пользователя в систему.

    Attributes:
        email: Email пользователя с валидацией формата.
        password: Пароль пользователя.
    """

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """
    Схема для ответа с данными пользователя.

    Используется при возвращении данных пользователя в API ответах.
    Не включает пароль и другие чувствительные данные.

    Attributes:
        email: Email пользователя.
        first_name: Имя пользователя.
        last_name: Фамилия пользователя.
        gender: Пол пользователя.

    Config:
        from_attributes: Разрешает создание экземпляра из ORM объектов.
    """
    email: EmailStr
    first_name: str
    last_name: str
    gender: str

    model_config = ConfigDict(from_attributes=True)


class ResendConfirmationRequest(BaseModel):
    """
    Схема для запроса повторной отправки email подтверждения.

    Attributes:
        email: Email пользователя, которому нужно отправить подтверждение.
    """

    email: EmailStr


class PasswordResetRequest(BaseModel):
    """
    Схема для запроса сброса пароля.

    Attributes:
        email: Email пользователя, который запросил сброс пароля.
    """

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """
    Схема для подтверждения сброса пароля.

    Используется для установки нового пароля после получения токена сброса.

    Attributes:
        token: Токен сброса пароля, отправленный на email пользователя.
        new_password: Новый пароль длиной не менее 6 символов.
        new_password_confirm: Подтверждение нового пароля.

    Raises:
        ValueError: Если new_password и new_password_confirm не совпадают.

    Example:
        ```json
        {
            "token": "abc123token456",
            "new_password": "newsecurepass456",
            "new_password_confirm": "newsecurepass456"
        }
        ```
    Примечание:
        Добавить проверку несовпадения со старым паролем?
    """

    token: str
    new_password: str = Field(min_length=6)
    new_password_confirm: str = Field(min_length=6)

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        """
        Проверяет совпадение нового пароля и его подтверждения.

        Args:
            v: Значение поля new_password_confirm.
            info: Контекст валидации с уже провалидированными данными.

        Returns:
            str: Значение new_password_confirm, если проверка пройдена.

        Raises:
            ValueError: Если пароли не совпадают.
        """

        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Пароли не совпадают.")
        return v


class UserInfoUpdate(BaseModel):
    """
    Схема для обновления информации о пользователе.

    Используется для частичного обновления профиля пользователя.

    Attributes:
        first_name: Новое имя пользователя.
        last_name: Новая фамилия пользователя.
        gender: Новый пол пользователя.

    Config:
        from_attributes: Разрешает создание экземпляра из ORM объектов.
    """

    first_name: str
    last_name: str
    gender: str

    model_config = ConfigDict(from_attributes=True)


class PasswordChange(BaseModel):
    """
    Схема для смены пароля пользователя.

    Требует указания текущего пароля для дополнительной безопасности.

    Attributes:
        current_password: Текущий пароль пользователя.
        new_password: Новый пароль длиной не менее 6 символов.
        new_password_confirm: Подтверждение нового пароля.

    Raises:
        ValueError: Если new_password и new_password_confirm не совпадают.
    """

    current_password: str
    new_password: str = Field(..., min_length=6)
    new_password_confirm: str = Field(..., min_length=6)

    @field_validator("new_password_confirm")
    @classmethod
    def passwords_match(cls, v: str, info: ValidationInfo) -> str:
        """
        Проверяет совпадение нового пароля и его подтверждения.

        Args:
            v: Значение поля new_password_confirm.
            info: Контекст валидации с уже провалидированными данными.

        Returns:
            str: Значение new_password_confirm, если проверка пройдена.

        Raises:
            ValueError: Если пароли не совпадают.
        """

        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Новые пароли не совпадают")
        return v
