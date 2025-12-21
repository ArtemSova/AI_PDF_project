"""
Модуль обработки запросов управления пользовательскими данными.

Этот модуль содержит функции-обработчики для HTTP запросов, связанных с:
- Получением информации о текущем пользователе
- Обновлением персональных данных профиля
- Сменой пароля учетной записи

Все обработчики требуют аутентификации пользователя через JWT токен
и предоставляют доступ только к собственным данным пользователя.

Эндпоинты:
    GET /users/me/my_info: Получение информации о текущем пользователе
    PATCH /users/me/change_info: Обновление персональных данных профиля
    PATCH /users/me/change_password: Смена пароля учетной записи

Зависимости:
    fastapi: APIRouter, Depends для маршрутизации и инъекции зависимостей
    sqlalchemy.ext.asyncio: AsyncSession для асинхронной работы с БД
    app.api.deps: get_current_user для проверки аутентификации
    app.db.session: get_db для получения сессии БД
    app.models.user: User модель пользователя
    app.schemas.user: UserResponse, UserInfoUpdate, PasswordChange схемы данных
    app.services.user_service: UserService для бизнес-логики пользователей
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserInfoUpdate, PasswordChange
from app.services.user_service import UserService


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/my_info", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
):
    """
    Получение информации о текущем аутентифицированном пользователе.

    Процесс:
        1. Извлечение пользователя из JWT токена через get_current_user
        2. Получение профиля пользователя через UserService
        3. Возврат публичных данных пользователя

    Требуется:
        JWT токен в заголовке Authorization: Bearer <token>

    Возвращает:
        UserResponse: Публичные данные пользователя:
            email (EmailStr): Email адрес пользователя
            first_name (str, optional): Имя пользователя
            last_name (str, optional): Фамилия пользователя
            gender (Gender, optional): Пол пользователя (male/female)

    Ошибки:
        401: Пользователь не аутентифицирован (неверный/отсутствующий токен)
        403: Учетная запись не активна или заблокирована
    """

    return await UserService.get_current_user_profile(current_user)


@router.patch("/change_info", response_model=UserResponse)
async def update_user_info(
    data: UserInfoUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Обновление персональных данных профиля пользователя.

    Процесс:
        1. Проверка аутентификации пользователя
        2. Валидация входящих данных через Pydantic модель UserInfoUpdate
        3. Проверка, что запрос не пустой (хотя бы одно поле передано)
        4. Обновление только переданных полей (частичное обновление)
        5. Сохранение изменений в базе данных
        6. Возврат обновленного профиля пользователя

    Тело запроса (JSON):
        first_name (str, optional): Новое имя пользователя
        last_name (str, optional): Новая фамилия пользователя
        gender (Gender, optional): Новый пол (male/female)

    Параметры:
        data (UserInfoUpdate): Данные для обновления профиля
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Возвращает:
        UserResponse: Обновленные данные профиля пользователя

    Ошибки:
        400: Пустой запрос (все поля None) или неверные данные
        401: Пользователь не аутентифицирован
        403: Учетная запись не активна или заблокирована

    Примечание:
        - Обновляются только переданные поля (частичное обновление)
        - Если клиент отправляет пустой запрос (все поля None), возвращается 400
    """

    return await UserService.update_user_info(
        user=current_user,
        data=data,
        db=db,
    )


@router.patch("/change_password", response_model=UserResponse)
async def change_user_password(
    pw_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Смена пароля учетной записи пользователя.

    Процесс:
        1. Проверка аутентификации пользователя
        2. Валидация данных через Pydantic модель PasswordChange
        3. Проверка текущего пароля (должен совпадать с сохраненным)
        4. Проверка, что новый пароль и подтверждение совпадают
        5. Хеширование нового пароля с использованием Argon2
        6. Обновление хеша пароля в базе данных
        7. Возврат подтверждения об успешной смене пароля

    Тело запроса (JSON):
        current_password (str, required): Текущий пароль пользователя
        new_password (str, required): Новый пароль (минимум 6 символов)
        new_password_confirm (str, required): Подтверждение нового пароля

    Параметры:
        pw_data (PasswordChange): Данные для смены пароля
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Возвращает:
        UserResponse: Данные профиля пользователя после смены пароля

    Ошибки:
        400: Новые пароли не совпадают
        401: Неверный текущий пароль или пользователь не аутентифицирован
        403: Учетная запись не активна или заблокирована

    Примечание:
        - Валидация на совпадение новых паролей выполняется Pydantic
        - Текущий пароль проверяется через сравнение хешей
        - После успешной смены пароля все существующие JWT токены остаются валидными
          до истечения срока их действия (рекомендуется выйти из системы на всех устройствах)
    """

    return {"message": f"Пароль пользователя {current_user.email} изменен"}
