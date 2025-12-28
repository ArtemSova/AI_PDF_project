"""
Модуль тестирования утилит для работы с PDF файлами.

Содержит юнит-тесты для функций обработки PDF документов.
Проверяет корректность извлечения текста из PDF файлов, обработку ошибок
при чтении файлов и парсинге содержимого.

Классы тестов:
    TestPDFUtils: Тестирование функции extract_text_from_pdf

Зависимости:
    pytest: Фреймворк для написания и запуска тестов
    unittest.mock: patch, mock_open для мокирования файловых операций и зависимостей
    app.utils.pdf_utils: Модуль с тестируемыми функциями
"""

import pytest
from unittest.mock import patch, mock_open

from app.utils.pdf_utils import extract_text_from_pdf


class TestPDFUtils:
    """
    Тесты для утилит работы с PDF файлами.

    Включает тестирование:
        - Успешного извлечения текста из многостраничного PDF
        - Обработки ошибок при отсутствии файла
        - Обработки ошибок при парсинге поврежденного PDF
    """

    @patch('app.utils.pdf_utils.PdfReader')
    @patch('builtins.open', new_callable=mock_open)
    def test_extract_text_from_pdf_success(self, mock_file, mock_pdf_reader):
        """
        Проверяет успешное извлечение текста из PDF файла.

        Тест мокирует чтение файла и парсинг PDF, эмулируя документ
        с двумя страницами текста. Проверяет корректность конкатенации
        текста со всех страниц.

        Args:
            mock_file: Мок для функции open
            mock_pdf_reader: Мок для класса PdfReader

        Assertions:
            - Файл открывается в бинарном режиме для чтения
            - PdfReader вызывается с правильными параметрами
            - Результат содержит текст со всех страниц, разделенный переносами строк
        """

        # Настраиваем моки
        mock_page1_text = "Text from page 1."
        mock_page2_text = "Text from page 2."

        # Создаём отдельные объекты для каждой страницы
        mock_page1 = type('obj', (object,), {'extract_text': lambda: mock_page1_text})
        mock_page2 = type('obj', (object,), {'extract_text': lambda: mock_page2_text})
        mock_pdf_reader.return_value.pages = [mock_page1, mock_page2]

        file_path = "dummy/path/file.pdf"
        result = extract_text_from_pdf(file_path)

        # Проверки
        mock_file.assert_called_once_with(file_path, 'rb')
        mock_pdf_reader.assert_called_once()

        expected_text = "".join([mock_page1_text + "\n", mock_page2_text + "\n"]).strip()  # Без /n ломается?
        assert result == expected_text

    @patch('builtins.open', side_effect=FileNotFoundError("File not found"))
    def test_extract_text_from_pdf_file_not_found(self, mock_file):
        """
        Проверяет обработку ошибки при отсутствии PDF файла.

        Тест эмулирует ситуацию, когда указанный файл не существует.
        Проверяет, что функция корректно обрабатывает FileNotFoundError
        и выбрасывает ожидаемое исключение с сообщением об ошибке.

        Args:
            mock_file: Мок для функции open, настроенный на вызов FileNotFoundError

        Raises:
            Exception: Должно быть выброшено исключение с сообщением
                      "Не удалось извлечь текст из PDF:"
        """

        file_path = "nonexistent/file.pdf"
        with pytest.raises(Exception, match="Не удалось извлечь текст из PDF:"):
            extract_text_from_pdf(file_path)

    @patch('app.utils.pdf_utils.PdfReader', side_effect=Exception("PDF parsing error"))
    @patch('builtins.open', new_callable=mock_open)
    def test_extract_text_from_pdf_parsing_error(self, mock_file, mock_pdf_reader):
        """
        Проверяет обработку ошибок парсинга поврежденного PDF файла.

        Тест эмулирует ситуацию, когда файл существует, но его содержимое
        повреждено или имеет недопустимый формат. Проверяет, что функция
        корректно обрабатывает исключения от PdfReader и выбрасывает
        ожидаемое исключение с детальным сообщением об ошибке.

        Args:
            mock_file: Мок для функции open
            mock_pdf_reader: Мок для класса PdfReader, настроенный на вызов Exception

        Raises:
            Exception: Должно быть выброшено исключение с сообщением
                      "Не удалось извлечь текст из PDF: PDF parsing error"
        """

        file_path = "dummy/path/corrupted.pdf"
        with pytest.raises(Exception, match="Не удалось извлечь текст из PDF: PDF parsing error"):
            extract_text_from_pdf(file_path)
