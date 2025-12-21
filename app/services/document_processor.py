"""
Модуль обработчика документов для загрузки и анализа PDF файлов.

Этот модуль предоставляет класс DocumentProcessor, который координирует процесс:
- Загрузки PDF файлов от пользователей
- Сохранения файлов на диск
- Извлечения текста из PDF
- Анализа текста через AI модели
- Сохранения результатов в базу данных

Все операции выполняются асинхронно и оптимизированы для работы в среде FastAPI:
- I/O операции (чтение/запись файлов) используют асинхронные библиотеки
- CPU-bound операции (парсинг PDF, анализ текста) выносятся в отдельные потоки
- Автоматическая очистка временных файлов при ошибках

Класс спроектирован для работы с различными AI анализаторами через паттерн стратегии,
что позволяет легко переключаться между разными моделями (локальными или облачными).

Зависимости:
    asyncio: Для асинхронных операций и работы с потоками
    aiofiles: Асинхронная работа с файлами
    fastapi: UploadFile, HTTPException, BackgroundTasks
    sqlalchemy.ext.asyncio: AsyncSession для асинхронной работы с БД
    app.models: Document, User модели
    app.services.pdf_analyzer_base: PDFAnalyzerBase - абстрактный класс анализатора
    app.utils.exceptions: DocumentAnalysisError - кастомные исключения
    app.utils.pdf_utils: extract_text_from_pdf - извлечение текста из PDF
    app.core.config: settings - настройки приложения
"""

import asyncio
import uuid
from pathlib import Path
from typing import Optional
import aiofiles
from fastapi import HTTPException, status, UploadFile, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.user import User
from app.services.pdf_analyzer_base import PDFAnalyzerBase
from app.utils.exceptions import DocumentAnalysisError
from app.utils.pdf_utils import extract_text_from_pdf
from app.core.config import settings


class DocumentProcessor:
    """
    Сервис-обработчик для загрузки и анализа PDF документов.

    Класс инкапсулирует всю логику обработки документа: от получения файла
    от пользователя до сохранения проанализированных данных в БД. Использует
    паттерн "Стратегия" для работы с различными AI анализаторами.

    Особенности:
        - Асинхронная обработка всех этапов
        - Автоматическая очистка временных файлов при ошибках
        - Поддержка фоновых задач через BackgroundTasks
        - Валидация MIME-типов файлов
        - Генерация уникальных имен файлов для избежания коллизий

    Атрибуты:
        analyzer (PDFAnalyzerBase): Анализатор для извлечения данных из текста.
            Задается при создании экземпляра класса.

    Пример использования:
        analyzer = PDFLLMAnalyzer()
        processor = DocumentProcessor(analyzer)
        document = await processor.process_document(file, user, db)
    """

    def __init__(self, analyzer: PDFAnalyzerBase):
        """
        Инициализация обработчика документов.

        Аргументы:
            analyzer (PDFAnalyzerBase): Анализатор для извлечения структурированных
                данных из текста документа. Должен реализовывать метод analyze_document.
                Может быть локальным (Ollama) или облачным (Mistral API) анализатором.
        """

        self.analyzer = analyzer


    # ------- Вспомогательные асинхронные утилиты ---------------------------------------------------------------------
    async def _save_upload_file(self, upload_file: UploadFile, dest_path: Path) -> None:
        """
        Асинхронное сохранение UploadFile на диск.

        Процесс:
            1. Открытие файла на запись в бинарном режиме через aiofiles
            2. Почтение файла частями по 1 MiB для экономии памяти
            3. Запись каждой части в выходной файл

        Аргументы:
            upload_file (UploadFile): Файл, загруженный пользователем через FastAPI.
                Содержит имя файла, MIME-тип и методы для чтения.
            dest_path (Path): Путь для сохранения файла на диске.
                Должен быть абсолютным путем.

        Исключения:
            IOError: При ошибках чтения/записи файла.
            OSError: При проблемах с файловой системой.

        Примечание:
            Используется буфер в 1 MiB для баланса между скоростью и потреблением памяти.
            Размер буфера можно регулировать в зависимости от требований приложения.
        """

        async with aiofiles.open(dest_path, "wb") as out_file:
            while chunk := await upload_file.read(1024 * 1024):  # размер буфера
                await out_file.write(chunk)


    async def _remove_file(self, path: Path) -> None:
        """
        Асинхронное удаление файла с диска.

        Процесс:
            1. Вызов синхронной функции os.unlink в отдельном потоке
            2. Использование параметра missing_ok=True для игнорирования ошибок,
               если файл уже был удален

        Аргументы:
            path (Path): Путь к файлу для удаления.

        Примечание:
            os.remove является синхронной операцией, поэтому оборачивается
            в asyncio.to_thread для неблокирующего выполнения.
        """

        await asyncio.to_thread(path.unlink, missing_ok=True)


    # -------- Основной процесс ---------------------------------------------------------------------------------------
    async def process_document(
        self,
        file: UploadFile,
        current_user: User,
        db: AsyncSession,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> Document:
        """
        Основной метод обработки документа от загрузки до сохранения в БД.

        Процесс:
            1. Валидация MIME-типа файла (должен быть PDF)
            2. Генерация уникального имени и пути для сохранения файла
            3. Асинхронное сохранение файла на диск
            4. Извлечение текста из PDF в отдельном потоке
            5. Анализ текста через AI анализатор
            6. Создание записи Document в базе данных
            7. Возврат созданного документа

        На любом этапе при ошибке выполняется очистка временного файла.

        Аргументы:
            file (UploadFile): PDF файл, загруженный пользователем.
                Должен иметь MIME-тип application/pdf.
            current_user (User): Пользователь, загрузивший документ.
                Его ID будет сохранен в поле user_id документа.
            db (AsyncSession): Асинхронная сессия базы данных.
                Используется для сохранения документа и коммита транзакции.
            background_tasks (BackgroundTasks, optional): Опциональный объект
                для добавления фоновых задач. В текущей реализации не используется,
                но оставлен для будущих расширений.

        Возвращает:
            Document: Созданный документ с заполненными полями:
                - document_number, document_date, sender, purpose, amount
                  (извлеченные анализатором)
                - file_path (путь к сохраненному файлу)
                - user_id (ID текущего пользователя)
                - created_at (время создания)

        Исключения:
            HTTPException 400: Если файл не PDF или не удалось извлечь текст
            HTTPException 400: Если анализ документа не удался (DocumentAnalysisError)
            HTTPException 500: Если ошибка при сохранении файла или анализе

        Пример использования:
            analyzer = PDFLLMAnalyzer()
            processor = DocumentProcessor(analyzer)
            document = await processor.process_document(file, current_user, db)

        Примечание:
            - Временные файлы удаляются при ошибках на этапах 4 и 5
            - Для извлечения текста используется отдельный поток, чтобы не блокировать event-loop
            - Анализатор должен быть асинхронным и обрабатывать свои ошибки
        """

        # 1. Валидация MIME‑типа
        if not file.content_type.startswith("application/pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Допустима загрузка только PDF‑файлов",
            )

        # 2. Подготовка уникального пути
        ext = Path(file.filename or "").suffix or ".pdf"
        unique_name = f"{uuid.uuid4()}{ext}"
        file_path = settings.UPLOAD_ROOT / unique_name

        # 3. Асинхронное сохранение файла
        try:
            await self._save_upload_file(file, file_path)
        except Exception as exc:
            # Ошибка I/O – файл, скорее всего, не успел создаться
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ошибка при сохранении файла: {exc}",
            )

        # 4. Выделяем текст из PDF – вынесено в отдельный поток
        try:
            # `extract_text_from_pdf` – обычная синхронная функция.
            # `asyncio.to_thread` (Python ≥3.9) автоматически использует пул потоков, не блокируя event‑loop.
            text_content: str = await asyncio.to_thread(
                extract_text_from_pdf, str(file_path)
            )
        except Exception as exc:
            # Не удалось распарсить PDF → чистим за собой
            await self._remove_file(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Не удалось извлечь текст из PDF: {exc}",
            )


        # 5. Анализ текста через пользовательский анализатор
        try:
            # `analyze_document` уже объявлена как async, но если внутри неё есть тяжёлый код – убедись,
            #  что в ней тоже используется asyncio.to_thread` или ProcessPoolExecutor.
            extracted_data = await self.analyzer.analyze_document(text_content)
        except DocumentAnalysisError as exc:
            await self._remove_file(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        except Exception as exc:
            # Любая другая ошибка аналитики → убираем файл
            await self._remove_file(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Ошибка анализа документа: {exc}",
            )

        # 6. Делаем запись в БД
        document = Document(
            document_number=extracted_data.get("document_number"),
            document_date=extracted_data.get("document_date"),
            sender=extracted_data.get("sender"),
            purpose=extracted_data.get("purpose"),
            amount=extracted_data.get("amount"),
            file_path=str(file_path),
            user_id=current_user.id,
        )

        db.add(document)
        await db.commit()
        await db.refresh(document)

        return document
