"""
Модуль обработки запросов работы с документами.

Этот модуль содержит функции-обработчики для HTTP запросов, связанных с:
- Загрузкой и обработкой PDF документов через различные AI движки
- Просмотром, редактированием и управлением документами
- Административным доступом к документам для руководителей

Все обработчики используют асинхронные сессии БД и реализуют проверку прав доступа
на основе ролей пользователей (менеджер, руководитель, администратор).

Эндпоинты:
    POST /documents/upload_local: Загрузка PDF с локальной LLM обработкой
    POST /documents/upload_mistral_online: Загрузка PDF через Mistral API
    POST /documents/upload_fallback: Загрузка PDF с автоматическим fallback-переключением (Ollama → Mistral)
    GET /documents/my_documents: Получение списка документов текущего пользователя
    GET /documents/show_{document_id}: Получение деталей конкретного документа
    GET /documents/update_{document_id}/edit: Получение данных документа для редактирования
    PATCH /documents/update_{document_id}: Обновление информации документа
    GET /documents/supervisor/all_docs: Получение всех документов (для руководителей)
    GET /documents/supervisor/doc_{document_id}: Получение любого документа по ID (для руководителей)

Зависимости:
    fastapi: APIRouter, Depends, UploadFile, File, HTTPException, status
    sqlalchemy.ext.asyncio: AsyncSession для асинхронной работы с БД
    typing: List для аннотаций списков
    app.api.deps: get_current_user, get_current_supervisor для проверки прав доступа
    app.db.session: get_db для получения сессии БД
    app.models.user: User модель пользователя
    app.schemas.document: Document, DocumentShort, DocumentSupervisorView, DocumentUpdate
    app.services.document_service: DocumentService для бизнес-логики документов
"""

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.api.deps import get_current_user, get_current_supervisor
from app.db.session import get_db
from app.models.user import User
from app.schemas.document import Document, DocumentShort, DocumentSupervisorView, DocumentUpdate
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload_local", response_model=Document)
async def upload_document(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Загрузка PDF документа с локальной обработкой через LLM.

    Процесс:
        1. Проверка роли пользователя (только менеджеры и администраторы)
        2. Валидация MIME-типа файла (должен быть PDF)
        3. Сохранение файла во временную директорию
        4. Извлечение текста из PDF файла
        5. Анализ текста через локальный LLM (Ollama с Mistral моделью)
        6. Извлечение структурированных данных (номер, дата, отправитель и т.д.)
        7. Сохранение документа в базу данных
        8. Возврат созданного документа

    Параметры:
        file (UploadFile): PDF файл для загрузки (обязательный)
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Формат запроса:
        multipart/form-data с полем 'file'

    Возвращает:
        Document: Созданный документ с заполненными полями

    Ошибки:
        400: Неверный формат файла или ошибка анализа документа
        403: Пользователь не имеет роли manager или admin
        500: Ошибка при обработке файла или анализе через LLM

    Примечание:
        Использует локальную LLM через Ollama, требует запущенного Ollama сервиса.
    """

    user_roles = [user_role.role.name for user_role in current_user.user_roles if user_role.is_active]
    if "manager" not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только менеджеры могут загружать документы"
        )

    return await DocumentService.upload_and_process_document(file, current_user, db)


@router.post("/upload_mistral_online", response_model=Document)
async def upload_document_with_mistral_api(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Загрузка PDF документа с обработкой через облачный Mistral API.

    Процесс:
        1. Проверка роли пользователя (только менеджеры и администраторы)
        2. Валидация MIME-типа файла (должен быть PDF)
        3. Сохранение файла во временную директорию
        4. Извлечение текста из PDF файла
        5. Отправка текста в Mistral API для анализа
        6. Извлечение структурированных данных из ответа API
        7. Сохранение документа в базу данных
        8. Возврат созданного документа

    Параметры:
        file (UploadFile): PDF файл для загрузки (обязательный)
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Формат запроса:
        multipart/form-data с полем 'file'

    Возвращает:
        Document: Созданный документ с заполненными полями

    Ошибки:
        400: Неверный формат файла или ошибка анализа документа
        403: Пользователь не имеет роли manager или admin
        500: Ошибка при обработке файла или работе с Mistral API

    Примечание:
        Требует настройки MISTRAL_API_KEY в переменных окружения.
        Использует облачный API Mistral, может иметь лимиты по запросам.
    """

    user_roles = [user_role.role.name for user_role in current_user.user_roles if user_role.is_active]
    if "manager" not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только менеджеры могут загружать документы"
        )

    return await DocumentService.upload_and_process_document_with_mistral_api(file, current_user, db)


@router.post("/upload_fallback", response_model=Document)
async def upload_document_fallback(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Загрузка PDF документа с автоматическим fallback-переключением между AI моделями.

    Этот эндпоинт использует LangGraph для реализации стратегии автоматического переключения
    между локальной моделью Ollama и облачной моделью Mistral AI в случае сбоев.

    Процесс обработки:
        1. Проверка прав доступа (только менеджеры и администраторы)
        2. Валидация типа файла (должен быть PDF)
        3. Если USE_LANGGRAPH_FALLBACK=True в настройках:
           - Попытка анализа через локальную модель Ollama
           - В случае ошибки - автоматический переход к Mistral API
        4. Если USE_LANGGRAPH_FALLBACK=False:
           - Используется только локальная модель Ollama

    Аргументы запроса:
        file (UploadFile, обязательный): PDF файл для обработки.
            Максимальный размер файла ограничен конфигурацией сервера.
            Поддерживаемый MIME-тип: application/pdf.

    Параметры авторизации:
        Требуется Bearer токен в заголовке Authorization.

    Требования к ролям пользователя:
        - manager: Менеджер (может загружать документы)
        - admin: Администратор (может загружать документы)

    Возвращает:
        Document: Созданный документ с заполненными полями

    Ошибки:
        400: Неверный формат файла или ошибка анализа документа
        401: Неавторизованный доступ (отсутствует или неверный токен)
        403: Пользователь не имеет роли manager или admin
        422: Ошибка валидации входных данных

    Конфигурационные зависимости:
        - OLLAMA_BASE_URL: URL сервера Ollama
        - OLLAMA_MODEL: Название модели Ollama
        - MISTRAL_API_KEY: API ключ для Mistral AI
        - MISTRAL_MODEL: Название модели Mistral (опционально)
        - USE_LANGGRAPH_FALLBACK: Флаг включения fallback-логики

    Примечания:
        При отключенном USE_LANGGRAPH_FALLBACK используется только Ollama
        Fallback срабатывает только при ошибках подключения к Ollama
        Для обработки используется только первый 4000 символов текста PDF
    """

    user_roles = [
        user_role.role.name
        for user_role in current_user.user_roles
        if user_role.is_active
    ]
    if "manager" not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Только менеджеры могут загружать документы",
        )

    return await DocumentService.upload_and_process_document_fallback(
        file, current_user, db
    )


@router.get("/my_documents", response_model=List[DocumentShort])
async def get_documents(
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Получение списка документов текущего пользователя с пагинацией.

    Процесс:
        1. Проверка аутентификации пользователя
        2. Получение документов пользователя из базы данных
        3. Применение пагинации (skip, limit)
        4. Возврат краткой информации о документах

    Параметры:
        skip (int): Количество записей для пропуска (по умолчанию 0)
        limit (int): Максимальное количество возвращаемых записей (по умолчанию 100)
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Возвращает:
        List[DocumentShort]: Список документов пользователя

    Ошибки:
        401: Пользователь не аутентифицирован
    """

    documents = await DocumentService.get_user_documents(
        user_id=current_user.id,
        db=db,
        skip=skip,
        limit=limit
    )
    return documents


@router.get("/show_{document_id}", response_model=Document)
async def get_document(
        document_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Получение детальной информации о конкретном документе.

    Процесс:
        1. Проверка аутентификации пользователя
        2. Поиск документа по ID с проверкой прав доступа
        3. Проверка, что документ принадлежит текущему пользователю
        4. Возврат полной информации о документе

    Параметры:
        document_id (int): ID документа для получения
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Возвращает:
        Document: Полная информация о документе

    Ошибки:
        401: Пользователь не аутентифицирован
        404: Документ не найден или у пользователя нет прав доступа
    """

    return await DocumentService.get_document_by_id(document_id, current_user.id, db)


@router.get("/update_{document_id}/edit", response_model=DocumentUpdate)
async def get_document_for_edit(
        document_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Получение данных документа для последующего редактирования.

    Процесс:
        1. Проверка аутентификации пользователя
        2. Поиск документа по ID с проверкой прав доступа
        3. Проверка, что документ принадлежит текущему пользователю
        4. Возврат только редактируемых полей документа

    Параметры:
        document_id (int): ID документа для редактирования
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Возвращает:
        DocumentUpdate: Только редактируемые поля документа

    Ошибки:
        401: Пользователь не аутентифицирован
        404: Документ не найден или у пользователя нет прав доступа
    """

    document = await DocumentService.get_document_by_id(document_id, current_user.id, db)
    return DocumentUpdate(
        document_number=document.document_number,
        document_date=document.document_date,
        sender=document.sender,
        purpose=document.purpose,
        amount=document.amount
    )

@router.patch("/update_{document_id}", response_model=Document)
async def update_document(
        document_id: int,
        document_update: DocumentUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    """
    Обновление информации о документе.

    Процесс:
        1. Проверка аутентификации пользователя
        2. Поиск документа по ID с проверкой прав доступа
        3. Проверка, что документ принадлежит текущему пользователю
        4. Обновление указанных полей документа
        5. Сохранение изменений в базе данных
        6. Возврат обновленного документа

    Параметры:
        document_id (int): ID документа для обновления
        document_update (DocumentUpdate): Данные для обновления
        current_user (User): Текущий аутентифицированный пользователь
        db (AsyncSession): Сессия базы данных

    Возвращает:
        Document: Обновленный документ

    Ошибки:
        401: Пользователь не аутентифицирован
        404: Документ не найден или у пользователя нет прав доступа
        400: Неверные данные для обновления

    Примечание:
        Обновляются только переданные поля (частичное обновление).
    """

    return await DocumentService.update_document(
        document_id=document_id,
        user_id=current_user.id,
        document_update=document_update,
        db=db
    )


@router.get("/supervisor/all_docs", response_model=List[DocumentSupervisorView])
async def get_all_documents_admin(
        skip: int = 0,
        limit: int = 100,
        current_director: User = Depends(get_current_supervisor),
        db: AsyncSession = Depends(get_db),
):
    """
    Получение всех документов из системы (только для руководителей).

    Процесс:
        1. Проверка прав доступа (роль supervisor или admin)
        2. Получение всех документов из базы данных
        3. Загрузка информации о пользователях для каждого документа
        4. Применение пагинации
        5. Добавление email пользователя к каждому документу
        6. Возврат списка документов с расширенной информацией

    Параметры:
        skip (int): Количество записей для пропуска (по умолчанию 0)
        limit (int): Максимальное количество возвращаемых записей (по умолчанию 100)
        current_director (User): Текущий пользователь с правами руководителя
        db (AsyncSession): Сессия базы данных

    Возвращает:
        List[DocumentSupervisorView]: Список всех документов с информацией о владельцах

    Ошибки:
        403: Пользователь не имеет прав руководителя
    """

    documents = await DocumentService.get_all_documents_for_supervisor(
        db=db,
        skip=skip,
        limit=limit
    )

    # Добавляем email пользователя к каждому документу
    result = []
    for doc in documents:
        doc_dict = doc.__dict__.copy()
        doc_dict['user_email'] = doc.user.email if doc.user else None
        result.append(DocumentSupervisorView(**doc_dict))

    return result


@router.get("/supervisor/doc_{document_id}", response_model=DocumentSupervisorView)
async def get_document_admin(
        document_id: int,
        current_director: User = Depends(get_current_supervisor),
        db: AsyncSession = Depends(get_db),
):
    """
    Получение любого документа по ID (только для руководителей).

    Процесс:
        1. Проверка прав доступа (роль supervisor или admin)
        2. Поиск документа по ID без проверки принадлежности пользователю
        3. Загрузка информации о пользователе-владельце документа
        4. Добавление email пользователя к документу
        5. Возврат документа с расширенной информацией

    Параметры:
        document_id (int): ID документа для получения
        current_director (User): Текущий пользователь с правами руководителя
        db (AsyncSession): Сессия базы данных

    Возвращает:
        DocumentSupervisorView: Документ с информацией о владельце

    Ошибки:
        403: Пользователь не имеет прав руководителя
        404: Документ не найден
    """

    document = await DocumentService.get_document_by_id_for_supervisor(document_id, db)

    # Добавляем email пользователя
    doc_dict = document.__dict__.copy()
    doc_dict['user_email'] = document.user.email if document.user else None

    return DocumentSupervisorView(**doc_dict)
