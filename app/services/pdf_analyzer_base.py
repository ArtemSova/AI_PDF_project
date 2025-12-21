"""
Абстрактный базовый класс для анализаторов PDF документов.

Этот модуль определяет абстрактный базовый класс PDFAnalyzerBase, который предоставляет
интерфейс и общую логику для анализа текста PDF документов с помощью различных AI моделей.
Класс использует паттерн "Шаблонный метод" для стандартизации процесса анализа:
создание промпта → анализ текста → парсинг ответа → конвертация типов.

Основные компоненты:
    PDFAnalyzerBase: Абстрактный базовый класс с методами для анализа документов
    Abstract методы: analyze_document - должен быть реализован в подклассах
    Конкретные методы: _create_prompt, _parse_response - общая логика для всех анализаторов

Особенности:
    - Поддержка JSON формата для структурированных ответов от AI моделей
    - Очистка ответов от Markdown разметки (```json ... ```)
    - Автоматическая конвертация типов (дата, десятичные числа)
    - Валидация наличия полезной информации в документе
    - Обработка ошибок парсинга и конвертации

Зависимости:
    abc: ABC, abstractmethod для создания абстрактных классов
    json: Парсинг JSON ответов от AI моделей
    logging: Логирование ошибок и информации
    datetime: Конвертация строк в объекты datetime
    decimal: Decimal для точного представления денежных сумм
    app.utils.exceptions: DocumentAnalysisError для ошибок анализа
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any
from datetime import datetime
from decimal import Decimal

from app.utils.exceptions import DocumentAnalysisError

logger = logging.getLogger(__name__)


class PDFAnalyzerBase(ABC):
    """
    Абстрактный базовый класс для анализаторов PDF документов.

    Определяет интерфейс и общую логику для извлечения структурированной информации
    из текста PDF документов с использованием различных AI моделей (локальных или облачных).

    Класс реализует паттерн "Шаблонный метод", где:
        - analyze_document() - абстрактный метод, который должен быть реализован в подклассах
        - _create_prompt() - создает стандартизированный промпт для всех анализаторов
        - _parse_response() - общая логика парсинга и валидации ответов

    Все конкретные анализаторы (PDFLLMAnalyzer, PDFMistralAnalyzer) должны наследоваться
    от этого класса и реализовывать метод analyze_document.

    Атрибуты:
        Нет атрибутов уровня экземпляра. Конфигурация должна передаваться через
        конструктор подклассов (например, API ключи, URL, модели).

    Пример использования в подклассе:
        class MyAnalyzer(PDFAnalyzerBase):
            async def analyze_document(self, text_content: str) -> Dict[str, Any]:
                # Реализация взаимодействия с конкретной AI моделью
                response = await self._call_ai_api(text_content)
                return self._parse_response(response)
    """

    @abstractmethod
    async def analyze_document(self, text_content: str) -> Dict[str, Any]:
        """
        Абстрактный метод для анализа текста документа.

        Должен быть реализован в подклассах. Отвечает за взаимодействие с конкретной
        AI моделью (локальной или облачной) и возврат сырого ответа от модели.

        Аргументы:
            text_content (str): Текст, извлеченный из PDF документа.
                Обычно обрезается до 4000 символов для экономии токенов.
                Содержит распознанный текст со всех страниц PDF.

        Возвращает:
            Dict[str, Any]: Словарь с извлеченными полями документа:
                - document_number (str, optional): Номер документа
                - document_date (str/datetime, optional): Дата документа в ISO формате
                - sender (str, optional): Отправитель документа
                - purpose (str, optional): Назначение платежа
                - amount (float/Decimal, optional): Сумма документа

        Исключения:
            DocumentAnalysisError: Если AI модель не может проанализировать документ
            Exception: Любые другие ошибки взаимодействия с AI моделью

        Примечание:
            Метод должен вызывать _parse_response для стандартизации обработки ответа.
            В случае ошибок AI модели должен логировать детали и выбрасывать исключения.
        """
        pass

    def _create_prompt(self, text_content: str) -> str:
        """
        Создает стандартизированный промпт для извлечения информации из текста документа.

        Промпт информирует AI модель о:
            - Требуемом формате ответа (JSON)
            - Полях для извлечения (document_number, document_date, sender, purpose, amount)
            - Важном замечании об организации "ООО «Моя фирма»"
            - Ограничении длины текста (первые 4000 символов)
            - Примере ожидаемого ответа

        Аргументы:
            text_content (str): Текст документа для анализа.
                Автоматически обрезается до 4000 символов для оптимизации использования токенов.

        Возвращает:
            str: Строка промпта, готового к отправке в AI модель.

        Примечание:
            - Нет необходимости в асинронном варианте, выполняется < 1 ms
            - Ограничение в 4000 символов балансирует между качеством анализа и стоимостью токенов
            - Пример ответа помогает модели понять ожидаемую структуру JSON
            - Явное указание "null" для отсутствующих полей предотвращает ошибки парсинга
            - Замечание об "ООО «Моя фирма»" помогает избежать ошибок идентификации отправителя
        """

        return f"""
        Проанализируй следующий текст документа и извлеки информацию в формате JSON.
        Если какое-то поле не найдено, поставь null.

        ВАЖНОЕ ЗАМЕЧАНИЕ: ООО «Моя фирма» это наша организация, а не отправитель.

        Текст документа:
        {text_content[:4000]}

        Извлеки следующие поля:
        - document_number: номер документа (строка)
        - document_date: дата документа в формате ISO (строка, например "2024-01-15T00:00:00")
        - sender: отправитель (юр. лицо) (строка)
        - purpose: назначение платежа (услуга/товар) (строка)
        - amount: сумма оплаты (число с плавающей точкой)

        Верни ТОЛЬКО корректный JSON-объект без дополнительного текста.
        Пример ответа:
        {{
            "document_number": "12345",
            "document_date": "2024-01-15T00:00:00",
            "sender": "ООО Ромашка",
            "purpose": "Оплата за товары по счету 123",
            "amount": 15000.00
        }}
        """

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """
        Парсит ответ от AI модели и конвертирует данные в нужные типы.

        Процесс:
            1. Очистка ответа от Markdown разметки (```json ... ```)
            2. Парсинг JSON строки в словарь Python
            3. Проверка наличия хотя бы одного полезного поля
            4. Конвертация строки даты в объект datetime (ISO формат)
            5. Конвертация числа в Decimal для точного представления денежных сумм
            6. Обработка ошибок парсинга и конвертации

        Аргументы:
            response_text (str): Ответ от AI модели, который должен содержать JSON объект.
                Может содержать Markdown разметку или дополнительные текстовые элементы.

        Возвращает:
            Dict[str, Any]: Словарь с проанализированными и конвертированными данными:
                - document_number (str, optional): Номер документа
                - document_date (datetime, optional): Дата документа как datetime объект
                - sender (str, optional): Отправитель документа
                - purpose (str, optional): Назначение платежа
                - amount (Decimal, optional): Сумма документа как Decimal

        Исключения:
            json.JSONDecodeError: Если ответ не является валидным JSON
            DocumentAnalysisError: Если документ не содержит полезной информации
            ValueError: Если дата не соответствует ISO формату

        Логирование:
            ERROR: При ошибках парсинга JSON с деталями ошибки и исходным ответом
            ERROR: При других ошибках парсинга ответа

        Примечание:
            - Нет необходимости в асинронном варианте, выполняется < 1 ms
            - Поля могут быть None, если AI модель вернула null или не нашла информацию
            - Decimal используется для точных финансовых расчетов (плавающая точка может давать ошибки)
            - Валидация полезности документа предотвращает создание пустых записей
        """

        try:
            # Очищаем ответ от markdown разметки
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Убираем ```json
            if response_text.endswith("```"):
                response_text = response_text[:-3]  # Убираем ```

            data = json.loads(response_text)

            # Проверяем, содержит ли документ полезную информацию
            useful_fields = ['document_number', 'document_date', 'sender', 'purpose', 'amount']
            has_useful_info = any(data.get(field) is not None for field in useful_fields)

            if not has_useful_info:
                raise DocumentAnalysisError("Документ не содержит необходимой информации")

            # Конвертируем дату
            if data.get("document_date") and isinstance(data["document_date"], str):
                try:
                    data["document_date"] = datetime.fromisoformat(data["document_date"])
                except ValueError:
                    data["document_date"] = None

            # Конвертируем сумму
            if data.get("amount") is not None:
                try:
                    data["amount"] = Decimal(str(data["amount"]))
                except:
                    data["amount"] = None

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {str(e)}")
            logger.error(f"Ответ: {response_text}")
            raise DocumentAnalysisError("Невозможно распознать структуру документа")
        except DocumentAnalysisError:
            # Перебрасываем наше исключение
            raise
        except Exception as e:
            logger.error(f"Ошибка при парсинге ответа: {str(e)}")
            raise DocumentAnalysisError("Ошибка при обработке результата анализа")

    def _get_default_values(self) -> Dict[str, Any]:
        """
        Возвращает словарь со значениями по умолчанию для случая, когда анализ не удался.

        Returns:
            Dict[str, Any]: Словарь с ключами и None значениями.
        """

        return {
            "document_number": None,
            "document_date": None,
            "sender": None,
            "purpose": None,
            "amount": None
        }
