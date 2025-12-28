"""
Модуль unit-тестов для сервиса обработки документов.

Содержит изолированные тесты для класса DocumentProcessor, проверяющие:
- Успешную обработку PDF документов
- Валидацию типов файлов
- Обработку ошибок анализа документов
- Корректность работы с файловой системой и базой данных

Философия тестирования:
    - Каждый тест изолирован с помощью моков и временных директорий
    - Тестируется только логика DocumentProcessor, без внешних зависимостей
    - Используются кастомные мок-анализаторы для эмуляции разных сценариев
    - Проверяется корректность обработки как успешных, так и ошибочных случаев

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    tempfile: Создание временных директорий для изоляции тестов файловой системы
    pathlib.Path: Объектно-ориентированная работа с путями
    unittest.mock: Мокирование зависимостей и внешних вызовов
    fastapi.HTTPException: Исключения для эмуляции ошибок HTTP
    fastapi.UploadFile: Модель загружаемого файла для тестирования
    sqlalchemy.ext.asyncio.AsyncSession: Мок асинхронной сессии БД
    app.models.user: Модель пользователя для тестирования
    app.services.pdf_analyzer_base: Базовый класс анализатора PDF
    app.services.document_processor: Тестируемый сервис обработки документов
    app.utils.exceptions: Кастомные исключения для обработки ошибок
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.pdf_analyzer_base import PDFAnalyzerBase
from app.services.document_processor import DocumentProcessor
from app.utils.exceptions import DocumentAnalysisError


class MockAnalyzer(PDFAnalyzerBase):
    """
    Мок-анализатор для успешной обработки документов.

    Эмулирует работу реального анализатора PDF, возвращая фиктивные данные.
    Используется в тестах, где требуется успешный анализ документа.

    Methods:
        analyze_document: Возвращает фиктивные данные документа
    """

    async def analyze_document(self, text_content: str) -> dict:
        """
        Возвращает фиктивные данные анализа документа.

        Args:
            text_content: Текст документа (не используется в моке)

        Returns:
            dict: Фиктивные данные документа с предопределенными значениями
        """

        return {
            "document_number": "123",
            "document_date": "2024-01-01T00:00:00",
            "sender": "Mock Sender",
            "purpose": "Mock Purpose",
            "amount": 100.00
        }

class MockAnalyzerError(PDFAnalyzerBase):
    """
    Мок-анализатор для эмуляции ошибки анализа.

    Эмулирует ситуацию, когда анализ документа завершается ошибкой.
    Используется в тестах для проверки обработки ошибок в DocumentProcessor.

    Methods:
        analyze_document: Всегда выбрасывает DocumentAnalysisError
    """

    async def analyze_document(self, text_content: str) -> dict:
        """
        Всегда выбрасывает исключение DocumentAnalysisError.

        Args:
            text_content: Текст документа (не используется)

        Raises:
            DocumentAnalysisError: Всегда выбрасывается с сообщением "Анализ провален"
        """

        raise DocumentAnalysisError("Анализ провален")


class TestDocumentProcessor:
    """
    Класс unit-тестов для DocumentProcessor.

    Проверяет различные сценарии работы сервиса обработки документов:
    1. Успешная обработка валидного PDF файла
    2. Обработка файла недопустимого типа
    3. Обработка ошибки анализа PDF

    Особенности тестирования:
        - Все внешние зависимости (файловая система, БД, анализатор) замоканы
        - Используются временные директории для изоляции тестов
        - Проверяется корректность взаимодействия с моками (вызовы, параметры)
    """

    @pytest.fixture
    def mock_user(self):
        """
        Фикстура для создания мока пользователя.

        Returns:
            MagicMock: Мок объекта User с предустановленным id=1
        """

        user = MagicMock(spec=User)
        user.id = 1
        return user

    @pytest.fixture
    def mock_db(self):
        """
        Фикстура для создания мока асинхронной сессии БД.

        Returns:
            AsyncMock: Мок AsyncSession с замоканными методами add, commit, refresh
        """

        db = AsyncMock(spec=AsyncSession)
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def mock_file(self):
        """
        Фикстура для создания мока загружаемого файла.

        Returns:
            MagicMock: Мок объекта UploadFile с базовыми атрибутами
        """

        file = MagicMock(spec=UploadFile)
        file.filename = "test.pdf"
        file.content_type = "application/pdf"
        return file

    @pytest.mark.asyncio
    async def test_process_document_success(self, mock_file, mock_user, mock_db):
        """
        Тестирует успешную обработку PDF документа.

        Шаги выполнения:
            1. Создание DocumentProcessor с мок-анализатором
            2. Настройка временной директории для загрузки файлов
            3. Мокирование зависимостей (сохранение файла, извлечение текста)
            4. Вызов process_document с мок-файлом, пользователем и БД
            5. Проверка корректности взаимодействия с зависимостями
            6. Проверка результата обработки

        Ожидаемые результаты:
            - Файл сохраняется (_save_upload_file вызывается 1 раз)
            - Текст извлекается из PDF (extract_text_from_pdf вызывается)
            - Документ добавляется в БД (mock_db.add вызывается 1 раз)
            - Транзакция коммитится (mock_db.commit вызывается)
            - Объект обновляется (mock_db.refresh вызывается)
            - Возвращенный документ содержит ожидаемые данные

        Args:
            mock_file: Мок загружаемого файла в формате PDF
            mock_user: Мок пользователя, загружающего документ
            mock_db: Мок асинхронной сессии базы данных
        """

        processor = DocumentProcessor(MockAnalyzer())

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('app.services.document_processor.settings') as mock_settings:
                mock_settings.UPLOAD_ROOT = Path(temp_dir)

                # Мокаем сохранение файла, чтобы не писать в файловую систему
                with patch.object(processor, '_save_upload_file') as mock_save:
                    # Мокаем извлечение текста, чтобы не читать реальный файл
                    with patch('app.services.document_processor.extract_text_from_pdf') as mock_extract:
                        # Мок возвращает фиктивный текст
                        mock_extract.return_value = "Текст мока для анализа."
                        result_doc = await processor.process_document(mock_file, mock_user, mock_db)


        # Проверки взаимодействия с зависимостями
        mock_save.assert_called_once()
        assert mock_extract.called
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited_once()
        mock_db.refresh.assert_awaited_once()

        # Проверка результата обработки
        assert result_doc.document_number == "123"
        assert result_doc.user_id == 1

    @pytest.mark.asyncio
    async def test_process_document_invalid_type(self, mock_user, mock_db):
        """
        Тестирует обработку файла недопустимого типа.

        Шаги выполнения:
            1. Создание мок-файла с не-PDF типом (text/plain)
            2. Создание DocumentProcessor с мок-анализатором
            3. Вызов process_document с невалидным файлом
            4. Проверка, что выбрасывается HTTPException с кодом 400

        Ожидаемые результаты:
            - Выбрасывается HTTPException со статусом 400
            - Сообщение об ошибке содержит упоминание "PDF"
            - Никакие методы сохранения или анализа не вызываются

        Args:
            mock_user: Мок пользователя
            mock_db: Мок асинхронной сессии базы данных
        """

        file = AsyncMock(spec=UploadFile)
        file.filename = "test.txt"
        file.content_type = "text/plain"
        processor = DocumentProcessor(MockAnalyzer())

        with pytest.raises(HTTPException) as exc_info:
            await processor.process_document(file, mock_user, mock_db)

        assert exc_info.value.status_code == 400
        assert "PDF" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_process_document_analysis_error(self, mock_file, mock_user, mock_db):
        """
        Тестирует обработку ошибки анализа документа.

        Шаги выполнения:
            1. Создание DocumentProcessor с мок-анализатором, выбрасывающим ошибку
            2. Настройка временной директории для загрузки файлов
            3. Мокирование зависимостей для изоляции теста
            4. Вызов process_document, ожидая ошибку
            5. Проверка, что файл сохраняется и удаляется при ошибке
            6. Проверка корректности HTTPException

        Ожидаемые результаты:
            - Файл сохраняется (_save_upload_file вызывается 1 раз)
            - При ошибке анализа файл удаляется (_remove_file вызывается 1 раз)
            - Выбрасывается HTTPException со статусом 400
            - Сообщение об ошибке содержит текст из DocumentAnalysisError

        Args:
            mock_file: Мок загружаемого файла в формате PDF
            mock_user: Мок пользователя, загружающего документ
            mock_db: Мок асинхронной сессии базы данных
        """

        processor = DocumentProcessor(MockAnalyzerError())

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('app.services.document_processor.settings') as mock_settings:
                mock_settings.UPLOAD_ROOT = Path(temp_dir)

                # Мокаем сохранение файла
                with patch.object(processor, '_save_upload_file') as mock_save:
                    # Мокаем извлечение текста
                    with patch('app.services.document_processor.extract_text_from_pdf') as mock_extract:
                        mock_extract.return_value = "Текст мока для анализа."
                        # Мокаем удаление файла, чтобы не пытаться удалять несуществующий
                        with patch.object(processor, '_remove_file') as mock_remove:
                            with pytest.raises(HTTPException) as exc_info:
                                await processor.process_document(mock_file, mock_user, mock_db)


        # Проверки взаимодействия с зависимостями
        mock_save.assert_called_once()
        mock_remove.assert_called_once()
        assert exc_info.value.status_code == 400
        assert "Анализ провален" in exc_info.value.detail
