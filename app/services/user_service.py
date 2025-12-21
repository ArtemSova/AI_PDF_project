"""
Сервисный слой для работы с пользователями.

Класс UserService предоставляет бизнес-логику для операций с пользователями:
- Регистрация новых пользователей и подтверждение по email
- Аутентификация пользователей и управление сессиями
- Восстановление и смена паролей
- Управление профилями пользователей
- Проверка статусов учетных записей (активность, блокировка)

Все методы статические и асинхронные, что обеспечивает:
- Простоту использования без создания экземпляров класса
- Эффективную работу с асинхронными сессиями SQLAlchemy
- Легкость тестирования и внедрения зависимостей

Особенности:
    - Двухэтапная регистрация с подтверждением по email
    - Поддержка JWT токенов разных типов (регистрация, сброс пароля, доступ)
    - Интеграция с системой отправки email для уведомлений
    - Автоматическая проверка статусов учетных записей
    - Изоляция бизнес-логики от слоя API и работы с базой данных
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User, Role, UserRole
from app.schemas.user import UserCreate, UserLogin, PasswordChange, UserInfoUpdate
from app.core.security import create_registration_token, verify_token, verify_password, create_auth_token, get_password_hash, create_password_reset_token
from app.core.email_sender import send_registration_email, send_password_reset_email


class UserService:
    """
    Сервис для бизнес-логики работы с пользователями.

    Класс содержит статические методы для всех операций с пользователями.
    Все методы работают асинхронно и возвращают либо словари с результатами,
    либо генерируют исключения в случае ошибок.

    Особенности архитектуры:
        - Использует Pydantic схемы для валидации входных данных
        - Инкапсулирует всю бизнес-логику, связанную с пользователями
        - Гарантирует целостность данных и проверку статусов учетных записей
        - Разделяет ответственность между аутентификацией, регистрацией и управлением профилями
    """

    @staticmethod
    async def register_user(
        user_in: UserCreate,
        db: AsyncSession,
    ):
        """
        Регистрация нового пользователя в системе.

        Процесс:
            1. Проверка совпадения паролей
            2. Проверка уникальности email в системе
            3. Создание пользователя с хешированным паролем и статусом is_active=False
            4. Назначение роли 'guest' новому пользователю
            5. Генерация JWT токена для подтверждения регистрации
            6. Отправка email с ссылкой для подтверждения

        Аргументы:
            user_in (UserCreate): Данные для регистрации пользователя, включая:
                - email (str): Email пользователя (должен быть уникальным)
                - password (str): Пароль пользователя
                - password_confirm (str): Подтверждение пароля
                - first_name (str): Имя пользователя
                - last_name (str): Фамилия пользователя
                - gender (str): Пол пользователя (опционально)
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Словарь с ключом 'message' и текстом о необходимости подтверждения по email.

        Исключения:
            HTTPException 400: Если пароли не совпадают
            HTTPException 400: Если email уже зарегистрирован в системе
            RuntimeError: Если роль 'guest' не найдена в базе данных

        Требования к безопасности:
            - Пароль хешируется с использованием Argon2
            - Учетная запись создается неактивной до подтверждения по email
            - JWT токен содержит минимальные необходимые данные (id и email)

        Конфигурация:
            Требует настройки JWT_SECRET_KEY и JWT_ALGORITHM (вписан сразу в config) в .env файле.
        """

        # 1. Проверка паролей
        if user_in.password != user_in.password_confirm:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Пароли не совпадают",
            )

        # 2. Проверка существования пользователя
        result = await db.execute(
            select(User).where(User.email == user_in.email)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email уже зарегистрирован в системе",
            )

        # 3. Создание пользователя
        new_user = User(
            email=user_in.email,
            password_hash=get_password_hash(user_in.password),
            is_active=False,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            gender=user_in.gender,
        )

        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)  # ← ВАЖНО

        # 3.1 Получаем роль guest
        result = await db.execute(
            select(Role).where(Role.name == "guest")
        )
        guest_role = result.scalar_one_or_none()

        if not guest_role:
            raise RuntimeError("Роль 'guest' не найдена в БД")

        # 3.2 Назначаем роль пользователю
        db.add(
            UserRole(
                user_id=new_user.id,
                role_id=guest_role.id,
            )
        )

        await db.commit()

        # 4. Генерация токена
        payload = {
            "sub": new_user.id,
            "email": new_user.email,
        }
        token = create_registration_token(payload)

        # 5. Отправка email
        await send_registration_email(
            to_email=new_user.email,
            token=token,
        )

        return {
            "message": "Регистрация успешна. Проверьте почту для подтверждения.",
        }

    @staticmethod
    async def confirm_registration(
        token: str,
        db: AsyncSession,
    ):
        """
        Активация учетной записи пользователя после подтверждения по email.

        Процесс:
            1. Верификация JWT токена и проверка его типа
            2. Извлечение user_id из полезной нагрузки токена
            3. Поиск пользователя в базе данных
            4. Проверка, что учетная запись еще не активирована
            5. Установка статуса is_active=True

        Аргументы:
            token (str): JWT токен подтверждения регистрации.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Сообщение о результате активации:
                - Если активация успешна: {"message": "Учетная запись активирована"}
                - Если уже активирована: {"message": "Учетная запись уже активирована"}

        Исключения:
            HTTPException 400: Если токен неверен, просрочен или имеет неверный тип
            HTTPException 400: Если в токене отсутствует user_id
            HTTPException 404: Если пользователь не найден

        Особенности:
            - Токен должен быть типа 'registration'
            - Пользователь должен существовать и иметь статус is_active=False
            - После активации пользователь может входить в систему
        """

        payload = verify_token(token)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Токен неверен или просрочен",
            )

        # Проверяем тип токена
        if payload.get("type") != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный тип токена",
            )

        user_id = int(payload.get("sub"))
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Недопустимое содержание токена",
            )

        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        if user.is_active:
            return {"message": "Учетная запись уже активирована"}

        user.is_active = True
        await db.commit()

        return {"message": "Учетная запись активирована"}


    @staticmethod
    async def login_user(user_in: UserLogin, db: AsyncSession) -> dict:
        """
        Аутентификация пользователя и получение JWT токена доступа.

        Процесс:
            1. Поиск пользователя по email в базе данных
            2. Проверка соответствия пароля с использованием Argon2
            3. Проверка статуса активности учетной записи
            4. Генерация JWT токена доступа

        Аргументы:
            user_in (UserLogin): Данные для входа, включая:
                - email (str): Email пользователя
                - password (str): Пароль пользователя
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Словарь с JWT токеном в формате:
                {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer"
                }

        Исключения:
            HTTPException 400: Если email или пароль неверны
            HTTPException 403: Если учетная запись не активирована

        Особенности:
            - Возвращаемый формат совместим со стандартом OAuth 2.0 Bearer Token
            - Токен должен передаваться в заголовке Authorization
            - Срок действия токена настраивается через JWT_ACCESS_TOKEN_EXPIRE_DAYS
        """

        # 1 Найдём пользователя по email
        result = await db.execute(select(User).where(User.email == user_in.email))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный email или пароль",
            )

        # 2 Проверяем пароль (argon2)
        if not verify_password(user_in.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный email или пароль",
            )

        # 3 Активен ли аккаунт?
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учётная запись не активирована",
            )

        # 4 Генерируем JWT‑access‑токен
        payload = {"sub": user.id, "email": user.email}
        access_token = create_auth_token(payload)

        return {"access_token": access_token, "token_type": "bearer"}


    @staticmethod
    async def resend_confirmation_email(email: str, db: AsyncSession):
        """
        Повторная отправка email для подтверждения регистрации.

        Процесс:
            1. Поиск пользователя по email
            2. Проверка статусов учетной записи (не активна, не заблокирована)
            3. Генерация нового токена подтверждения
            4. Отправка email с подтверждением

        Аргументы:
            email (str): Email пользователя, которому нужно отправить подтверждение.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Сообщение о результате отправки письма.

        Исключения:
            HTTPException 404: Если пользователь не найден
            HTTPException 400: Если учетная запись уже активирована
            HTTPException 403: Если учетная запись заблокирована

        Особенности:
            - Отправляется только для неактивных и незаблокированных учетных записей
            - Генерируется новый токен с текущей временной меткой
            - Ссылка в email ведет на эндпоинт подтверждения регистрации
        """

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        if user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Учетная запись уже активирована",
            )

        if user.is_blocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учетная запись заблокирована",
            )

        payload = {"sub": user.id, "email": user.email}
        token = create_registration_token(payload)
        await send_registration_email(to_email=user.email, token=token)

        return {"message": "Письмо подтверждение отправлено."}


    @staticmethod
    async def request_password_reset(email: str, db: AsyncSession):
        """
        Инициация процесса сброса пароля.

        Процесс:
            1. Поиск пользователя по email
            2. Проверка статусов учетной записи (активна, не заблокирована)
            3. Генерация JWT токена сброса пароля
            4. Отправка email со ссылкой для сброса пароля

        Аргументы:
            email (str): Email пользователя, запросившего сброс пароля.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Сообщение о результате отправки письма.

        Исключения:
            HTTPException 404: Если пользователь не найден
            HTTPException 403: Если учетная запись не активна или заблокирована

        Особенности:
            - Токен имеет тип 'reset' для предотвращения misuse
            - Срок действия токена сброса пароля короче, чем у токена доступа
            - Ссылка в email ведет на форму ввода нового пароля (пока без шаблона)
        """

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учетная запись не активна",
            )

        if user.is_blocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учетная запись заблокирована",
            )

        payload = {"sub": user.id, "email": user.email}
        token = create_password_reset_token(payload)
        await send_password_reset_email(to_email=user.email, token=token)

        return {"message": "Письмо сброса пароля отправлено."}


    @staticmethod
    async def confirm_password_reset(token: str, new_password: str,
                                    db: AsyncSession):
        """
        Подтверждение сброса пароля и установка нового пароля.

        Процесс:
            1. Верификация JWT токена сброса пароля
            2. Извлечение user_id из полезной нагрузки токена
            3. Поиск пользователя в базе данных
            4. Проверка, что учетная запись не заблокирована
            5. Хеширование и сохранение нового пароля

        Аргументы:
            token (str): JWT токен сброса пароля.
            new_password (str): Новый пароль для установки.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Сообщение об успешном сбросе пароля.

        Исключения:
            HTTPException 400: Если токен неверен, просрочен или имеет неверный тип
            HTTPException 404: Если пользователь не найден
            HTTPException 403: Если учетная запись заблокирована

        Требования к безопасности:
            - Новый пароль хешируется перед сохранением
            - Старый пароль полностью заменяется
            - После сброса все существующие сессии остаются активными (стоит доработать)
        """

        payload = verify_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Токен неверен или просрочен",
            )
        if payload.get("type") != "reset":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Неверный тип токена",
            )
        user_id = int(payload.get("sub"))
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )
        # (Опционально) проверяем, не заблокирован ли пользователь:
        if user.is_blocked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Учетная запись заблокирована",
            )

        user.password_hash = get_password_hash(new_password)
        await db.commit()
        return {"message": "Пароль успешно сброшен"}

    @staticmethod
    async def get_current_user_profile(user: User) -> dict:
        """
        Получение профиля текущего аутентифицированного пользователя.

        Аргументы:
            user (User): ORM-объект текущего пользователя, полученный из dependency injection.

        Возвращает:
            dict: Словарь с основными данными профиля пользователя:
                {
                    "id": 123,
                    "email": "user@example.com",
                    "first_name": "Иван",
                    "last_name": "Иванов",
                    "gender": "male"
                }

        Особенности:
            - Не выполняет запросов к базе данных (работает с уже загруженным объектом)
            - Возвращает только безопасные для публикации поля
            - Не включает хеш пароля и системные статусы (is_active, is_blocked)
        """

        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "gender": user.gender,
        }

    @staticmethod
    async def update_user_info(
            user: User,
            data: UserInfoUpdate,
            db: AsyncSession,
    ) -> dict:
        """
        Обновление информации профиля пользователя.

        Процесс:
            1. Извлечение только переданных полей (частичное обновление)
            2. Проверка, что есть хотя бы одно поле для обновления
            3. Обновление атрибутов ORM-объекта
            4. Сохранение изменений в базе данных

        Аргументы:
            user (User): ORM-объект текущего пользователя.
            data (UserInfoUpdate): Данные для обновления (Pydantic схема).
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Обновленный профиль пользователя (через get_current_user_profile).

        Исключения:
            HTTPException 400: Если нет полей для обновления (все значения None).

        Особенности:
            - Использует model_dump(exclude_unset=True) для частичного обновления
            - Обновляет только те поля, которые явно переданы в запросе
            - Поддерживает обновление любых полей, определенных в UserInfoUpdate
        """

        # Приводим модель к dict, отфильтровываем None
        upd_dict = {k: v for k, v in data.model_dump().items() if v is not None}
        if not upd_dict:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nothing to update",
            )

        # Обновляем атрибуты ORM‑объекта
        for field, value in upd_dict.items():
            setattr(user, field, value)

        await db.commit()
        await db.refresh(user)

        return await UserService.get_current_user_profile(user)


    @staticmethod
    async def change_user_password(
            user: User,
            pw_data: PasswordChange,
            db: AsyncSession,
    ) -> dict:
        """
        Смена пароля текущего пользователя.

        Процесс:
            1. Проверка текущего пароля
            2. Хеширование нового пароля
            3. Сохранение нового хеша пароля в базе данных

        Аргументы:
            user (User): ORM-объект текущего пользователя.
            pw_data (PasswordChange): Данные для смены пароля, включая:
                - current_password (str): Текущий пароль для проверки
                - new_password (str): Новый пароль для установки
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            dict: Обновленный профиль пользователя.

        Исключения:
            HTTPException 401: Если текущий пароль неверен.

        Требования к безопасности:
            - Проверка текущего пароля обязательна
            - Новый пароль должен соответствовать политике сложности
            - После смены пароля все существующие сессии остаются активными (стоит доработать)
        """

        # 1 Проверка текущего пароля
        if not verify_password(pw_data.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid current password",
            )

        # 2 Хэшируем и записываем новый
        user.password_hash = get_password_hash(pw_data.new_password)

        await db.commit()
        await db.refresh(user)

        return await UserService.get_current_user_profile(user)
