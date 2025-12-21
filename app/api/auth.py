"""
Модуль обработки запросов аутентификации и авторизации.

Содержит функции-обработчики для HTTP запросов, связанных с:
- Регистрацией и подтверждением email пользователей
- Аутентификацией и выходом из системы
- Повторной отправкой подтверждающих писем
- Сбросом и восстановлением пароля

Все обработчики используют асинхронные сессии БД и JWT токены для безопасности.
Валидация данных осуществляется через Pydantic схемы.

Эндпоинты:
    POST /auth/register: Регистрация нового пользователя
    GET /auth/confirm: Подтверждение email по токену
    POST /auth/login: Вход в систему (возвращает JWT токен)
    POST /auth/logout: Выход из системы
    POST /auth/resend-confirmation: Повторная отправка подтверждения
    POST /auth/password-reset-request: Запрос сброса пароля
    POST /auth/password-reset-confirm: Подтверждение сброса пароля

Зависимости:
    fastapi: APIRouter, Depends, HTTPException, status
    sqlalchemy.ext.asyncio: AsyncSession для асинхронной работы с БД
    app.schemas.user: UserCreate, UserLogin, ResendConfirmationRequest,
                      PasswordResetRequest, PasswordResetConfirm
    app.schemas.token: Token (схема ответа с JWT)
    app.services.user_service: UserService для бизнес-логики
    app.db.session: get_db для получения сессии БД
    app.api.deps: get_current_user, login_form для проверки токенов и формы входа
"""

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.user import UserCreate, UserLogin, ResendConfirmationRequest, PasswordResetRequest, PasswordResetConfirm
from app.schemas.token import Token
from app.services.user_service import UserService
from app.db.session import get_db
from app.api.deps import get_current_user, login_form


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Регистрация нового пользователя.

    Процесс:
        1. Валидация данных через Pydantic модель UserCreate
        2. Проверка совпадения паролей (password и password_confirm)
        3. Проверка уникальности email в системе
        4. Хеширование пароля с использованием Argon2
        5. Создание пользователя с флагом is_active=False
        6. Назначение роли 'guest' по умолчанию
        7. Генерация JWT токена подтверждения
        8. Отправка email с подтверждением на указанный адрес

    Тело запроса (JSON):
        email (EmailStr, required): Email адрес (валидируется)
        password (str, required): Пароль (минимум 6 символов)
        password_confirm (str, required): Подтверждение пароля
        first_name (str, optional): Имя пользователя
        last_name (str, optional): Фамилия пользователя
        gender (Gender, optional): Пол (male/female)

    Ответы:
        200 - успешная регистрация, письмо отправлено на email
        400 - неверные данные, пароли не совпадают, email уже зарегистрирован
        500 - внутренняя ошибка сервера при отправке email
    """

    return await UserService.register_user(user_in, db)

@router.get("/register-confirm")
async def confirm_registration(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Подтверждение регистрации по токену из email.

    Процесс:
        1. Верификация JWT токена (тип 'registration')
        2. Извлечение user_id из payload токена
        3. Поиск пользователя по ID
        4. Активация аккаунта (установка is_active=True)
        5. Сохранение изменений в БД

    Параметры запроса:
        token (str, required): JWT токен из ссылки подтверждения

    Ответы:
        200 - учетная запись активирована или уже была активирована ранее
        400 - токен неверен, просрочен или имеет неверный тип
        404 - пользователь не найден
    """

    return await UserService.confirm_registration(token, db)


@router.post("/login", response_model=Token)
async def login(
    user_in: UserLogin = Depends(login_form),   # уже проверенный объект
    db: AsyncSession = Depends(get_db),
):
    """
    Аутентификация пользователя и получение JWT токена.

    Процесс:
        1. Преобразование OAuth2 формы в UserLogin (валидация email)
        2. Поиск активного пользователя по email
        3. Проверка пароля с использованием Argon2
        4. Проверка статуса аккаунта (is_active, is_blocked)
        5. Генерация JWT access токена (тип 'access', срок 30 дней)

    Тело запроса (form-data):
        username (str, required): Email адрес пользователя
        password (str, required): Пароль пользователя

    Ответы:
        200 - успешный вход, возвращает access_token
        400 - неверный email или пароль
        403 - учетная запись не активирована или заблокирована
    """

    return await UserService.login_user(user_in, db)

@router.post("/logout")
async def logout(
    current_user = Depends(get_current_user),  # токен обязателен
):
    """
    Выход из системы (символический).

    Примечание:
        В JWT-аутентификации токены являются stateless, поэтому
        физически удалить токен нельзя. Этот эндпоинт служит для
        уведомления клиента о необходимости удалить токен на стороне клиента.

    Требуется:
        JWT токен в заголовке Authorization: Bearer <token>

    Ответы:
        200 - успешный выход (клиент должен удалить токен)
        401 - отсутствует или неверный токен
    """

    return {"message": f"Пользователь {current_user.email} вышел"}

@router.post("/resend-confirm")
async def resend_confirmation(
    payload: ResendConfirmationRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Повторная отправка письма с подтверждением регистрации.

    Процесс:
        1. Поиск пользователя по email
        2. Проверка, что аккаунт еще не активирован (is_active=False)
        3. Проверка, что аккаунт не заблокирован (is_blocked=False)
        4. Генерация нового токена подтверждения
        5. Отправка письма с подтверждением

    Тело запроса (JSON):
        email (EmailStr, required): Email адрес для повторной отправки

    Ответы:
        200 - письмо отправлено успешно
        400 - учетная запись уже активирована
        403 - учетная запись заблокирована
        404 - пользователь не найден
    """

    return await UserService.resend_confirmation_email(payload.email, db)


@router.post("/password-reset-request")
async def password_reset_request(
    payload: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Запрос сброса пароля. Отправляет email со ссылкой для сброса.

    Процесс:
        1. Поиск активного и незаблокированного пользователя по email
        2. Генерация JWT токена сброса (тип 'reset', срок 30 минут)
        3. Отправка письма со ссылкой для сброса пароля

    Тело запроса (JSON):
        email (EmailStr, required): Email адрес для сброса пароля

    Ответы:
        200 - письмо с инструкциями отправлено (даже если email не найден)
        403 - учетная запись не активна или заблокирована
    """

    return await UserService.request_password_reset(payload.email, db)


@router.post("/password-reset-confirm")
async def password_reset_confirm(
    payload: PasswordResetConfirm,        # Содержит сравнение паролей
    db: AsyncSession = Depends(get_db),
):
    """
    Подтверждение сброса пароля с использованием токена из email.

    Процесс:
        1. Валидация токена (тип 'reset', срок действия)
        2. Проверка совпадения нового пароля и подтверждения
        3. Поиск пользователя по ID из токена
        4. Проверка, что аккаунт не заблокирован
        5. Хеширование нового пароля
        6. Сохранение нового пароля в БД

    Тело запроса (JSON):
        token (str, required): JWT токен из письма сброса пароля
        new_password (str, required): Новый пароль (минимум 6 символов)
        new_password_confirm (str, required): Подтверждение нового пароля

    Ответы:
        200 - пароль успешно изменен
        400 - токен неверен/просрочен, неверный тип токена, пароли не совпадают
        403 - учетная запись заблокирована
        404 - пользователь не найден
    """

    return await UserService.confirm_password_reset(
        token=payload.token,
        new_password=payload.new_password,
        db=db,
    )
