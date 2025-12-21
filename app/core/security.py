"""
Модуль безопасности и работы с JWT токенами.

Этот модуль предоставляет функции для:
- Хеширования и проверки паролей с использованием алгоритма Argon2
- Создания и проверки JWT (JSON Web Tokens) токенов разных типов
- Управления временем жизни токенов

Поддерживаемые типы токенов:
    registration: Для подтверждения email при регистрации (срок 2 часа)
    access: Для аутентификации и доступа к API (срок 30 дней)
    reset: Для сброса пароля (срок 30 минут)

Все токены подписываются с использованием секретного ключа из настроек приложения
и алгоритма HS256 по умолчанию.

Зависимости:
    passlib.context: CryptContext для хеширования паролей Argon2
    jose.jwt: Создание и проверка JWT токенов
    datetime: Работа с датами и временем жизни токенов
    .config: Настройки приложения (JWT_SECRET, ALGORITHM)
"""

from datetime import datetime, timedelta
from passlib.context import CryptContext
from typing import Optional
from jose import JWTError, jwt
from .config import settings


# Контекст для хеширования паролей с использованием Argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """
    Хеширование пароля с использованием алгоритма Argon2.

    Аргументы:
        password (str): Пароль в чистом виде для хеширования

    Возвращает:
        str: Хеш пароля, готовый для хранения в базе данных

    Примечание:
        Argon2 является победителем конкурса Password Hashing Competition (2015)
        и обеспечивает устойчивость к атакам перебором и атакам с использованием
        специализированного оборудования (ASIC/GPU).
    """

    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверка соответствия пароля его хешу.

    Аргументы:
        plain_password (str): Пароль в чистом виде для проверки
        hashed_password (str): Хеш пароля из базы данных

    Возвращает:
        bool: True если пароль соответствует хешу, иначе False

    Примечание:
        Функция автоматически определяет алгоритм хеширования и параметры
        из самого хеша, что позволяет безболезненно менять алгоритмы в будущем.
    """

    return pwd_context.verify(plain_password, hashed_password)


def create_registration_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Создание JWT токена для подтверждения регистрации.

    Процесс:
        1. Копирование данных для избежания мутаций
        2. Преобразование поля 'sub' (subject) в строку если присутствует
        3. Установка времени истечения (2 часа по умолчанию)
        4. Добавление типа токена 'registration'
        5. Подписание токена с использованием JWT_SECRET

    Аргументы:
        data (dict): Данные для включения в токен (обычно содержит 'sub' и 'email')
        expires_delta (timedelta, optional): Кастомный срок жизни токена

    Возвращает:
        str: JWT токен в закодированном виде

    Пример использования:
        token = create_registration_token({"sub": user_id, "email": user_email})

    Примечание:
        Токен используется в письмах подтверждения регистрации.
        Содержит тип 'registration' для различения от других токенов.
    """

    to_encode = data.copy()

    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=2)

    to_encode.update({
        "exp": expire,
        "type": "registration"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_auth_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Создание JWT access токена для аутентификации.

    Процесс:
        1. Копирование данных для избежания мутаций
        2. Преобразование поля 'sub' (subject) в строку если присутствует
        3. Установка времени истечения (30 дней по умолчанию)
        4. Добавление типа токена 'access'
        5. Подписание токена с использованием JWT_SECRET

    Аргументы:
        data (dict): Данные для включения в токен (обычно содержит 'sub' и 'email')
        expires_delta (timedelta, optional): Кастомный срок жизни токена

    Возвращает:
        str: JWT токен в закодированном виде

    Пример использования:
        token = create_auth_token({"sub": user_id, "email": user_email})

    Примечание:
        Токен используется для аутентификации пользователей при доступе к API.
        Клиенты должны передавать его в заголовке Authorization: Bearer <token>
    """

    to_encode = data.copy()

    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=30)

    to_encode.update({
        "exp": expire,
        "type": "access"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """
    Проверка и декодирование JWT токена.

    Процесс:
        1. Декодирование токена с использованием JWT_SECRET
        2. Проверка подписи токена
        3. Проверка срока действия токена (exp claim)
        4. Возврат payload токена если все проверки пройдены

    Аргументы:
        token (str): JWT токен в закодированном виде

    Возвращает:
        Optional[dict]: payload токена если токен валиден, иначе None

    Исключения:
        JWTError: Если токен невалиден, просрочен или имеет неверную подпись

    Примечание:
        Функция не проверяет тип токена - это должна делать вызывающая сторона.
        Для проверки типа токена используйте payload.get("type").
    """

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        return None


def create_password_reset_token(data: dict, expires_delta: Optional[timedelta] = None):
    """
    Создание JWT токена для сброса пароля.

    Процесс:
        1. Копирование данных для избежания мутаций
        2. Преобразование поля 'sub' (subject) в строку если присутствует
        3. Установка времени истечения (30 минут по умолчанию)
        4. Добавление типа токена 'reset'
        5. Подписание токена с использованием JWT_SECRET

    Аргументы:
        data (dict): Данные для включения в токен (обычно содержит 'sub' и 'email')
        expires_delta (timedelta, optional): Кастомный срок жизни токена

    Возвращает:
        str: JWT токен в закодированном виде

    Пример использования:
        token = create_password_reset_token({"sub": user_id, "email": user_email})

    Примечание:
        Токен используется в письмах для сброса пароля.
        Имеет короткий срок жизни (30 минут) из соображений безопасности.
        Содержит тип 'reset' для различения от других токенов.
    """

    to_encode = data.copy()

    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # 30 минут по‑умолчанию
        expire = datetime.utcnow() + timedelta(minutes=30)

    to_encode.update({
        "exp": expire,
        "type": "reset"
    })

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt
