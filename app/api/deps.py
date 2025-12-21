"""
Модуль зависимостей (Dependency Injection) для аутентификации и авторизации.

Этот модуль предоставляет функции-зависимости FastAPI для:
- Извлечения и проверки JWT токенов из заголовков запроса
- Получения текущего аутентифицированного пользователя
- Проверки прав доступа пользователя на основе ролей
- Преобразования данных формы входа в Pydantic модели

Все зависимости используют асинхронные сессии БД и работают с JWT токенами
типа 'access'. Поддерживается как обязательная, так и опциональная аутентификация.

Основные функции:
    get_current_user: Извлечение пользователя из access токена (обязательная)
    get_current_user_optional: Опциональное извлечение пользователя
    login_form: Преобразование OAuth2 формы в валидированную модель входа
    get_current_supervisor: Проверка наличия роли supervisor или admin

Зависимости:
    fastapi: Depends, HTTPException, status, OAuth2PasswordBearer, OAuth2PasswordRequestForm
    pydantic: ValidationError для валидации email
    sqlalchemy.ext.asyncio: AsyncSession для асинхронной работы с БД
    sqlalchemy.orm: selectinload для загрузки связанных данных
    sqlalchemy: select для построения запросов
    app.db.session: get_db для получения сессии БД
    app.models.user: User, UserRole модели пользователей
    app.core.security: verify_token для проверки JWT токенов
    app.schemas.user: UserLogin схема данных входа
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select
from fastapi.security import OAuth2PasswordRequestForm

from app.db.session import get_db
from app.models.user import User, UserRole
from app.core.security import verify_token
from app.schemas.user import UserLogin


# OAuth2‑Password‑Flow – путь к нашему login‑эндпоинту
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Получение текущего аутентифицированного пользователя из JWT access токена.

    Процесс:
        1. Извлечение токена из заголовка Authorization по схеме Bearer
        2. Проверка наличия токена (вызов 401 при отсутствии)
        3. Верификация токена с помощью verify_token
        4. Проверка типа токена (должен быть 'access')
        5. Извлечение user_id (subject) из payload токена
        6. Поиск пользователя в БД по ID с загрузкой ролей
        7. Проверка статуса пользователя (is_active, is_blocked)

    Аргументы:
        token (str): JWT токен из заголовка Authorization: Bearer <token>
        db (AsyncSession): Асинхронная сессия базы данных

    Возвращает:
        User: Объект пользователя со всеми данными и загруженными ролями

    Исключения:
        HTTPException 401: Если токен отсутствует, неверен, имеет не тот тип
                          или не содержит user_id
        HTTPException 403: Если пользователь заблокирован (is_blocked=True)
                          или не активирован (is_active=False)

    Примечание:
        Использует жадную загрузку (selectinload) для ролей пользователя,
        чтобы избежать проблемы N+1 запросов.
    """

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Не аутентифицирован",
        )

    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен",
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен другого типа",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Токен без идентификатора пользователя",
        )

    result = await db.execute(
        select(User)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
        .where(User.id == int(user_id))
    )

    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )

    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь не активен",
        )
    return user


def login_form(
    form_data: OAuth2PasswordRequestForm = Depends(),
) -> UserLogin:
    """
    Преобразование данных формы входа OAuth2 в валидированную модель UserLogin.

    Процесс:
        1. Получение данных формы входа от OAuth2PasswordRequestForm
        2. Создание объекта UserLogin с email=username и паролем
        3. Валидация email через Pydantic (EmailStr)
        4. При ошибке валидации - генерация HTTP 400

    Аргументы:
        form_data (OAuth2PasswordRequestForm): Данные формы входа
            username (str): Email пользователя
            password (str): Пароль пользователя

    Возвращает:
        UserLogin: Валидированный объект данных входа

    Исключения:
        HTTPException 400: Если email не соответствует формату EmailStr

    Примечание:
        OAuth2 стандарт использует поле 'username' для идентификатора,
        в нашем случае это email. Формат email валидируется Pydantic.
    """

    try:
        return UserLogin(email=form_data.username, password=form_data.password)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некорректный e‑mail",
        )


async def get_current_supervisor(
        current_user: User = Depends(get_current_user),
) -> User:
    """
    Проверка наличия прав руководителя у текущего пользователя.

    Процесс:
        1. Получение текущего пользователя через get_current_user
        2. Извлечение списка активных ролей пользователя
        3. Проверка наличия роли 'supervisor' или 'admin' в активных ролях
        4. При отсутствии требуемых ролей - генерация HTTP 403

    Аргументы:
        current_user (User): Объект текущего пользователя (из get_current_user)

    Возвращает:
        User: Тот же объект пользователя, если у него есть права руководителя

    Исключения:
        HTTPException 403: Если у пользователя нет роли supervisor или admin

    Примечание:
        Проверяются только активные роли (UserRole.is_active=True).
        Для выполнения операций достаточно любой из двух ролей: supervisor или admin.
    """

    user_roles = [user_role.role.name for user_role in current_user.user_roles if user_role.is_active]

    if "supervisor" not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только руководители могут выполнять эту операцию"
        )

    return current_user
