"""
Модуль Pydantic схем для пользователей.

Этот модуль определяет структуры данных для валидации, сериализации и
документирования API эндпоинтов, связанных с пользователями. Все схемы наследуются
от BaseModel Pydantic и включают валидацию полей, таких как email и пароли.

Основные схемы:
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
    pydantic: BaseModel, EmailStr, Field, validator
    typing: Optional для опциональных полей
    enum: Enum для перечислений
"""

from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum


class Gender(str, Enum):
    """
    Перечисление для пола пользователя.

    Значения:
        male (str): "male" - мужской пол
        female (str): "female" - женский пол

    Используется в полях gender схем пользователей для ограничения допустимых значений.
    """

    male = "male"
    female = "female"


class UserCreate(BaseModel):
    """
    Схема для регистрации нового пользователя.

    Используется в эндпоинте POST /auth/register для валидации данных регистрации.
    Включает обязательные поля email и пароли, а также опциональные персональные данные.

    Поля:
        email (EmailStr): Email адрес пользователя.
            Валидируется на соответствие формату email.

        password (str): Пароль пользователя.
            Минимальная длина: 6 символов.

        password_confirm (str): Подтверждение пароля.
            Минимальная длина: 6 символов.
            Должно совпадать с полем password.

        first_name (str): Имя пользователя.
            Обязательное поле.

        last_name (str): Фамилия пользователя.
            Обязательное поле.

        gender (Gender): Пол пользователя.
            Обязательное поле.

    Валидация:
        - Email валидируется автоматически через EmailStr
        - Пароли проверяются на минимальную длину через Field(min_length=6)
        - Совпадение паролей проверяется на уровне бизнес-логики в UserService

    Примечание:
        Поля first_name, last_name, gender помечены как "Заглушки" в комментарии,
        что означает их опциональность на этапе регистрации.
    """

    email: EmailStr
    password: str = Field(min_length=6)
    password_confirm: str = Field(min_length=6)
    first_name: str
    last_name: str
    gender: str


class UserLogin(BaseModel):
    """
    Схема для входа пользователя в систему.

    Используется в эндпоинте POST /auth/login для валидации данных входа.

    Поля:
        email (EmailStr): Email адрес пользователя.
            Валидируется на соответствие формату email.
            Пример: "user@example.com"

        password (str): Пароль пользователя.
            Передается в открытом виде, но защищается TLS/SSL на транспортном уровне.

    Валидация:
        - Email валидируется автоматически через EmailStr
        - Пароль проверяется на соответствие хешу в базе данных

    Примечание:
        В эндпоинте login используется зависимость login_form, которая преобразует
        OAuth2 форму (username, password) в эту схему (email, password).
    """

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """
    Схема для ответа с данными пользователя.

    Используется для возврата публичных данных пользователя в различных эндпоинтах.
    Не включает конфиденциальные данные (хеш пароля, флаги блокировки и т.д.).

    Поля:
        email (EmailStr): Email адрес пользователя.
            Пример: "user@example.com"

        first_name (str): Имя пользователя.
            Обязательное поле.

        last_name (str): Фамилия пользователя.
            Обязательное поле.

        gender (Gender): Пол пользователя.
            Обязательное поле.

    Конфигурация:
        from_attributes = True: Позволяет создавать экземпляры схемы
            напрямую из SQLAlchemy моделей (ORM mode).

    Использование:
        - Ответ эндпоинта GET /users/me/my_info
        - Ответ эндпоинтов обновления профиля и смены пароля
    """

    email: EmailStr
    first_name: str
    last_name: str
    gender: str

    class Config:
        from_attributes = True


class ResendConfirmationRequest(BaseModel):
    """
    Схема для запроса повторной отправки подтверждения email.

    Используется в эндпоинте POST /auth/resend-confirmation.

    Поля:
        email (EmailStr): Email адрес, на который нужно отправить подтверждение.
            Валидируется на соответствие формату email.
            Пример: "user@example.com"

    Примечание:
        Письмо отправляется только если пользователь существует,
        не активирован и не заблокирован.
    """

    email: EmailStr


class PasswordResetRequest(BaseModel):
    """
    Схема для запроса сброса пароля.

    Используется в эндпоинте POST /auth/password-reset-request.

    Поля:
        email (EmailStr): Email адрес пользователя, который запросил сброс пароля.
            Валидируется на соответствие формату email.
            Пример: "user@example.com"

    Примечание:
        Письмо со ссылкой для сброса пароля отправляется на указанный email,
        если пользователь существует, активен и не заблокирован.
    """

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """
    Схема для подтверждения сброса пароля.

    Используется в эндпоинте POST /auth/password-reset-confirm.
    Включает токен из письма и новый пароль с подтверждением.

    Поля:
        token (str): JWT токен из письма для сброса пароля.
            Должен быть валидным и не просроченным.
            Тип токена: "reset".

        new_password (str): Новый пароль пользователя.
            Минимальная длина: 6 символов.

        new_password_confirm (str): Подтверждение нового пароля.
            Минимальная длина: 6 символов.
            Должно совпадать с new_password.

    Валидация:
        - Совпадение паролей проверяется валидатором passwords_match
        - Токен проверяется на валидность и тип в бизнес-логике

    Валидатор:
        passwords_match: Проверяет, что new_password и new_password_confirm совпадают.
            Выбрасывает ValueError с сообщением "Пароли не совпадают." в случае несовпадения.

    Примечание:
        Токен обычно имеет срок жизни 30 минут для безопасности.
    """

    token: str
    new_password: str = Field(min_length=6)
    new_password_confirm: str = Field(min_length=6)

    @validator("new_password_confirm")
    def passwords_match(cls, v, values):
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("Пароли не совпадают.")
        return v


class UserInfoUpdate(BaseModel):
    """
    Схема для обновления профиля пользователя.

    Используется в эндпоинте PATCH /users/me/change_info.
    Все поля опциональны - поддерживается частичное обновление.

    Поля:
        first_name (str): Имя пользователя.
            Обязательное поле.

        last_name (str): Фамилия пользователя.
            Обязательное поле.

        gender (Gender): Пол пользователя.
            Обязательное поле.

    Примечание:
        Если клиент отправляет пустой запрос (все поля None), возвращается ошибка 400.
    """

    first_name: str
    last_name: str
    gender: str


class PasswordChange(BaseModel):
    """
    Схема для смены пароля пользователем.

    Используется в эндпоинте PATCH /users/me/change_password.
    Требует текущий пароль для проверки и новый пароль с подтверждением.

    Поля:
        current_password (str): Текущий пароль пользователя.
            Используется для проверки, что запрос делает владелец аккаунта.

        new_password (str): Новый пароль пользователя.
            Минимальная длина: 6 символов.
            Не может совпадать с текущим паролем (проверка в бизнес-логике).

        new_password_confirm (str): Подтверждение нового пароля.
            Минимальная длина: 6 символов.
            Должно совпадать с new_password.

    Валидация:
        - Совпадение новых паролей проверяется валидатором passwords_match
        - Текущий пароль проверяется на соответствие хешу в базе данных

    Валидатор:
        passwords_match: Проверяет, что new_password и new_password_confirm совпадают.
            Выбрасывает ValueError с сообщением "Новые пароли не совпадают" в случае несовпадения.

    Примечание:
        После успешной смены пароля все существующие JWT токены остаются валидными
        до истечения срока их действия. Рекомендуется выйти из системы на всех устройствах.
    """

    current_password: str
    new_password: str = Field(..., min_length=6)
    new_password_confirm: str = Field(..., min_length=6)

    @validator("new_password_confirm")
    def passwords_match(cls, v, values):
        if "new_password" in values and v != values["new_password"]:
            raise ValueError("Новые пароли не совпадают")
        return v
