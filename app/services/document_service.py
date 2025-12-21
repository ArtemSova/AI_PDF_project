"""
Сервисный слой для работы с документами.

Класс DocumentService предоставляет бизнес-логику для операций с документами:
- Загрузка и обработка PDF документов через различные AI движки
- Получение документов пользователя с пагинацией
- Проверка прав доступа к документам
- Обновление информации о документах
- Административные функции для руководителей

Все методы статические и асинхронные, что обеспечивает:
- Простоту использования без создания экземпляров класса
- Эффективную работу с асинхронными сессиями SQLAlchemy
- Легкость тестирования и внедрения зависимостей

Особенности:
    - Разделение методов для обычных пользователей и руководителей
    - Автоматическая проверка прав доступа к документам
    - Поддержка пагинации для методов, возвращающих списки
    - Изоляция бизнес-логики от слоя API и работы с файлами
"""

from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status, UploadFile
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentUpdate
from app.services.pdf_llm_analyzer import PDFLLMAnalyzer, PDFMistralAnalyzer
from app.services.document_processor import DocumentProcessor


class DocumentService:
    """
    Сервис для бизнес-логики работы с документами.

    Класс содержит статические методы для всех операций с документами.
    Все методы работают асинхронно и возвращают либо один Document, либо список Document.

    Особенности архитектуры:
        - Использует паттерн "Стратегия" для поддержки разных AI анализаторов
        - Инкапсулирует всю бизнес-логику, связанную с документами
        - Гарантирует целостность данных и проверку прав доступа
        - Разделяет ответственность между обработкой файлов и работой с БД
    """

    @staticmethod
    async def upload_and_process_document(
            file: UploadFile,
            current_user: User,
            db: AsyncSession,
    ) -> Document:
        """
        Загрузка PDF документа с локальной обработкой через Ollama.

        Процесс:
            1. Создание анализатора PDFLLMAnalyzer для локальной LLM обработки
            2. Создание DocumentProcessor для координации процесса обработки
            3. Запуск полного цикла: сохранение файла → извлечение текста → AI анализ → сохранение в БД

        Аргументы:
            file (UploadFile): PDF файл для загрузки. Должен иметь MIME-тип application/pdf.
            current_user (User): Аутентифицированный пользователь, загружающий документ.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            Document: Созданный документ с извлеченными AI данными.

        Исключения:
            HTTPException 400: Если файл не PDF или анализ не удался.
            HTTPException 500: Если ошибка при сохранении файла или работе с LLM.

        Требования к пользователю:
            Только пользователи с ролью 'manager' или 'admin' могут вызывать этот метод.

        Конфигурация:
            Требует настройки OLLAMA_BASE_URL и OLLAMA_MODEL в .env файле.
        """

        analyzer = PDFLLMAnalyzer()
        processor = DocumentProcessor(analyzer)
        return await processor.process_document(file, current_user, db)

    @staticmethod
    async def upload_and_process_document_with_mistral_api(
            file: UploadFile,
            current_user: User,
            db: AsyncSession,
    ) -> Document:
        """
        Загрузка PDF документа с облачной обработкой через Mistral API.

        Процесс:
            1. Создание анализатора PDFMistralAnalyzer для облачной обработки
            2. Создание DocumentProcessor для координации процесса обработки
            3. Запуск полного цикла: сохранение файла → извлечение текста → AI анализ через API → сохранение в БД

        Аргументы:
            file (UploadFile): PDF файл для загрузки. Должен иметь MIME-тип application/pdf.
            current_user (User): Аутентифицированный пользователь, загружающий документ.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            Document: Созданный документ с извлеченными AI данными.

        Исключения:
            HTTPException 400: Если файл не PDF или анализ не удался.
            HTTPException 500: Если ошибка при сохранении файла или работе с Mistral API.

        Требования к пользователю:
            Только пользователи с ролью 'manager' или 'admin' могут вызывать этот метод.

        Конфигурация:
            Требует настройки MISTRAL_API_KEY, MISTRAL_BASE_URL и MISTRAL_MODEL в .env файле.
        """

        analyzer = PDFMistralAnalyzer()
        processor = DocumentProcessor(analyzer)
        return await processor.process_document(file, current_user, db)


    @staticmethod
    async def get_user_documents(
            user_id: int,
            db: AsyncSession,
            skip: int = 0,
            limit: int = 10,
    ) -> List[Document]:
        """
        Получение списка документов пользователя с пагинацией.

        Аргументы:
            user_id (int): ID пользователя, чьи документы нужно получить.
            db (AsyncSession): Асинхронная сессия базы данных.
            skip (int): Количество документов для пропуска (для пагинации). По умолчанию 0.
            limit (int): Максимальное количество возвращаемых документов. По умолчанию 10.

        Возвращает:
            List[Document]: Список документов пользователя.

        Особенности:
            - Использует пагинацию через offset и limit для оптимизации работы с большими наборами данных
            - Возвращает документы в порядке их создания (без явной сортировки)
            - Не загружает связанные данные (пользователь) для оптимизации производительности
        """

        result = await db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_document_by_id(
            document_id: int,
            user_id: int,
            db: AsyncSession,
    ) -> Document:
        """
        Получение документа по ID с проверкой прав доступа.

        Процесс:
            1. Поиск документа по ID и user_id
            2. Проверка, что документ существует и принадлежит указанному пользователю
            3. Возврат документа или ошибки 404

        Аргументы:
            document_id (int): ID документа для получения.
            user_id (int): ID пользователя для проверки прав доступа.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            Document: Найденный документ.

        Исключения:
            HTTPException 404: Если документ не найден или не принадлежит пользователю.

        Особенности:
            - Гарантирует, что пользователь может получить только свои документы
            - Используется в обычных пользовательских эндпоинтах
            - Не загружает связанные данные для оптимизации
        """

        result = await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Документ не найден или у вас нет прав на его просмотр"
            )

        return document

    @staticmethod
    async def get_document_by_id_for_update(
            document_id: int,
            user_id: int,
            db: AsyncSession,
    ) -> Document:
        """
        Получение документа по ID с проверкой прав доступа (для последующего обновления).

        Примечание:
            Метод идентичен get_document_by_id, возможно на проде для фронта можно его
            переиспользовать для получения изменяемых данных.

        Аргументы:
            document_id (int): ID документа для получения.
            user_id (int): ID пользователя для проверки прав доступа.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            Document: Найденный документ.

        Исключения:
            HTTPException 404: Если документ не найден или не принадлежит пользователю.
        """

        result = await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Документ не найден или у вас нет прав на его просмотр"
            )

        return document

    @staticmethod
    async def update_document(
            document_id: int,
            user_id: int,
            document_update: DocumentUpdate,
            db: AsyncSession,
    ) -> Document:
        """
        Обновление информации о документе пользователя.

        Процесс:
            1. Получение документа с проверкой прав доступа
            2. Извлечение только переданных полей для обновления (частичное обновление)
            3. Обновление полей документа
            4. Сохранение изменений в БД и возврат обновленного документа

        Аргументы:
            document_id (int): ID документа для обновления.
            user_id (int): ID пользователя для проверки прав доступа.
            document_update (DocumentUpdate): Данные для обновления (Pydantic схема).
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            Document: Обновленный документ.

        Исключения:
            HTTPException 404: Если документ не найден или не принадлежит пользователю.

        Особенности:
            - Использует model_dump(exclude_unset=True) для частичного обновления
            - Обновляет только те поля, которые явно переданы в запросе
            - Автоматически обновляет поле updated_at через триггер базы данных
        """

        result = await db.execute(
            select(Document)
            .where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Документ не найден или недостаточно прав для редактирования"
            )

        update_data = document_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)

        await db.commit()
        await db.refresh(document)

        return document


    @staticmethod
    async def get_all_documents_for_supervisor(
            db: AsyncSession,
            skip: int = 0,
            limit: int = 100,
    ) -> List[Document]:
        """
        Получение всех документов системы для руководителей.

        Аргументы:
            db (AsyncSession): Асинхронная сессия базы данных.
            skip (int): Количество документов для пропуска (для пагинации). По умолчанию 0.
            limit (int): Максимальное количество возвращаемых документов. По умолчанию 100.

        Возвращает:
            List[Document]: Список всех документов с информацией о пользователях.

        Особенности:
            - Загружает связанные данные (пользователь) через selectinload для оптимизации
            - Сортирует документы по дате создания (новые первыми)
            - Использует пагинацию для работы с большими наборами данных
            - Только для пользователей с ролью 'supervisor' или 'admin'

        Запрос оптимизирован:
            SELECT documents.*, users.* FROM documents
            LEFT JOIN users ON documents.user_id = users.id
            ORDER BY documents.created_at DESC
            LIMIT :limit OFFSET :skip
        """

        result = await db.execute(
            select(Document)
            .options(selectinload(Document.user))  # Загружаем информацию о пользователе
            .offset(skip)
            .limit(limit)
            .order_by(Document.created_at.desc())
        )
        return result.scalars().all()

    @staticmethod
    async def get_document_by_id_for_supervisor(
            document_id: int,
            db: AsyncSession,
    ) -> Document:
        """
        Получение любого документа по ID для руководителей.

        Процесс:
            1. Поиск документа по ID без проверки принадлежности пользователю
            2. Загрузка информации о пользователе-владельце документа
            3. Возврат документа или ошибки 404

        Аргументы:
            document_id (int): ID документа для получения.
            db (AsyncSession): Асинхронная сессия базы данных.

        Возвращает:
            Document: Найденный документ с информацией о пользователе.

        Исключения:
            HTTPException 404: Если документ не найден.

        Особенности:
            - Не проверяет принадлежность документа - позволяет руководителям просматривать любые документы
            - Загружает связанные данные (пользователь) через selectinload
            - Только для пользователей с ролью 'supervisor' или 'admin'
        """

        result = await db.execute(
            select(Document)
            .options(selectinload(Document.user))
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Документ не найден"
            )

        return document
