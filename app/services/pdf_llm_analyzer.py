"""
Конкретные реализации анализаторов PDF документов с использованием различных AI моделей.

Этот модуль предоставляет классы-анализаторы, которые реализуют абстрактный базовый класс
PDFAnalyzerBase и используют разные AI модели для извлечения структурированной информации
из текста PDF документов.

Доступные анализаторы:
    PDFLLMAnalyzer: Использует локальную модель Ollama через синхронный интерфейс LangChain
    PDFMistralAnalyzer: Использует облачную модель Mistral AI через асинхронный API

Особенности:
    - Единый интерфейс анализа через PDFAnalyzerBase
    - Поддержка как локальных (Ollama), так и облачных (Mistral) моделей
    - Асинхронная архитектура с сохранением отзывчивости event-loop
    - Автоматическая обработка различных форматов ответов от разных моделей
    - Централизованная обработка ошибок и логирование
    - Конвертация типов данных (строки → datetime, числа → Decimal) в базовом классе

Основные компоненты:
    PDFLLMAnalyzer: Анализатор для локальных моделей Ollama
    PDFMistralAnalyzer: Анализатор для облачного API Mistral AI

Зависимости:
    asyncio: Для асинхронного выполнения и работы с потоками
    logging: Для логирования ошибок и отладки
    typing: Для аннотаций типов
    langchain_core.messages: Для обработки ответов от Chat-моделей
    langchain_ollama: Клиент для локальных моделей Ollama
    langchain_mistralai: Клиент для облачного API Mistral AI
    app.core.config: Настройки приложения (API ключи, URL моделей)
    app.services.pdf_analyzer_base: Базовый класс анализатора
    app.utils.exceptions: Пользовательские исключения (LLMServiceError)

Примечания:
    - PDFLLMAnalyzer использует синхронный клиент Ollama, поэтому вызовы оборачиваются в asyncio.to_thread
    - PDFMistralAnalyzer использует нативный асинхронный клиент Mistral
    - Оба анализатора возвращают данные в одинаковом формате благодаря общему базовому классу
    - Все исключения от AI моделей оборачиваются в LLMServiceError
    - DocumentAnalysisError и DocumentParsingError могут быть выброшены при парсинге ответа
"""

import logging
import asyncio
from typing import Dict, Any

from langchain_core.messages import AIMessage
from langchain_ollama import OllamaLLM
from langchain_mistralai import ChatMistralAI

from app.core.config import settings
from app.services.pdf_analyzer_base import PDFAnalyzerBase
from app.utils.exceptions import LLMServiceError


logger = logging.getLogger(__name__)


class PDFLLMAnalyzer(PDFAnalyzerBase):
    """
    Анализатор PDF документов с использованием локальной модели Ollama.

    Класс реализует взаимодействие с локально запущенной моделью Ollama через
    синхронный клиент LangChain. Для сохранения асинхронной природы приложения
    и предотвращения блокировки event-loop, синхронные вызовы оборачиваются в
    asyncio.to_thread.

    Особенности:
        - Использует локальную модель Ollama (например, llama2, mistral, codellama)
        - Работает через синхронный интерфейс LangChain (OllamaLLM.invoke)
        - Автоматическое обертывание в отдельный поток для асинхронности
        - Конфигурация через настройки приложения (OLLAMA_MODEL, OLLAMA_BASE_URL)
        - Все ошибки взаимодействия с моделью оборачиваются в LLMServiceError

    Атрибуты:
        _llm (OllamaLLM): Экземпляр синхронного клиента для работы с Ollama.
            Инициализируется в конструкторе с параметрами из настроек.

    Примечания:
        - Требует запущенного сервера Ollama по адресу из settings.OLLAMA_BASE_URL
        - Низкая температура (0.1) обеспечивает детерминированные и точные ответы
        - При ошибках создания клиента могут быть выброшены стандартные исключения Python
    """

    def __init__(self) -> None:
        """
        Инициализирует анализатор с конфигурацией из настроек приложения.

        Создает экземпляр OllamaLLM с параметрами:
            - model: Название модели из settings.OLLAMA_MODEL
            - base_url: URL сервера Ollama из settings.OLLAMA_BASE_URL
            - temperature: 0.1 для детерминированных ответов

        Исключения:
            Exception: Могут возникнуть стандартные исключения Python при создании клиента
                (например, если сервер Ollama недоступен или параметры невалидны)
        """

        self._llm = OllamaLLM(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.1,
        )

    async def analyze_document(self, text_content: str) -> Dict[str, Any]:
        """
        Анализирует текст документа с помощью локальной модели Ollama.

        Процесс:
            1. Создает промпт с помощью _create_prompt (унаследован от базового класса)
            2. Вызывает синхронный метод OllamaLLM.invoke в отдельном потоке через asyncio.to_thread
            3. Обрабатывает возможные исключения (сеть, сервер, модель)
            4. Передает сырой ответ в _parse_response для стандартизированной обработки

        Аргументы:
            text_content (str): Текст, извлеченный из PDF документа.
                Обычно обрезается до 4000 символов в методе _create_prompt.

        Возвращает:
            Dict[str, Any]: Словарь с извлеченными полями документа:
                - document_number (str, optional): Номер документа
                - document_date (datetime, optional): Дата документа как объект datetime
                - sender (str, optional): Отправитель
                - purpose (str, optional): Назначение платежа
                - amount (Decimal, optional): Сумма как Decimal

        Исключения:
            LLMServiceError: Если не удается связаться с Ollama или возникла ошибка модели
            DocumentAnalysisError: Если не удается распознать структуру документа (из _parse_response)
            DocumentParsingError: Если документ не содержит полезной информации (из _parse_response)

        Логирование:
            WARNING: При ошибках взаимодействия с Ollama (с exc_info=False)

        Примечания:
            - Использует asyncio.to_thread для предотвращения блокировки event-loop
            - Оборачивает исключения от Ollama в LLMServiceError
            - Полагается на _parse_response для обработки JSON и конвертации типов
            - Возвращаемые типы конвертируются в datetime и Decimal в базовом классе
        """

        prompt = self._create_prompt(text_content)

        try:
            raw_answer = await asyncio.to_thread(self._llm.invoke, prompt)
        except Exception as exc:
            logger.warning("Ollama запрос завершился ошибкой (fallback): %s", exc, exc_info=False)
            raise LLMServiceError("Не удалось связаться с Ollama") from exc

        return self._parse_response(raw_answer)


class PDFMistralAnalyzer(PDFAnalyzerBase):
    """
    Анализатор PDF документов с использованием облачной модели Mistral AI.

    Класс реализует взаимодействие с облачным API Mistral через асинхронный
    клиент LangChain. Использует нативный асинхронный интерфейс (ainvoke),
    что позволяет эффективно работать в асинхронном окружении.

    Особенности:
        - Использует облачные модели Mistral AI (mistral-large-latest и другие)
        - Работает через асинхронный интерфейс LangChain (ChatMistralAI.ainvoke)
        - Нативная асинхронность без необходимости обертки в потоки
        - Автоматическая обработка объектов AIMessage из LangChain
        - Конфигурация через настройки приложения (MISTRAL_API_KEY, MISTRAL_MODEL)
        - Все ошибки взаимодействия с API оборачиваются в LLMServiceError

    Атрибуты:
        _llm (ChatMistralAI): Экземпляр асинхронного клиента для работы с Mistral AI.
            Инициализируется в конструкторе с API ключом и параметрами модели.

    Примечания:
        - Требует валидного API ключа в settings.MISTRAL_API_KEY
        - По умолчанию использует модель "mistral-large-latest"
        - Ограничение max_tokens=1000 предотвращает излишнее потребление токенов
        - Низкая температура (0.1) обеспечивает детерминированные ответы
    """

    def __init__(self) -> None:
        """
        Инициализирует анализатор с API ключом Mistral и параметрами модели.

        Создает экземпляр ChatMistralAI с параметрами:
            - model_name: Из settings.MISTRAL_MODEL или "mistral-large-latest" по умолчанию
            - api_key: Ключ API из settings.MISTRAL_API_KEY
            - temperature: 0.1 для детерминированных ответов
            - max_tokens: 1000 для ограничения длины ответа

        Исключения:
            RuntimeError: Если MISTRAL_API_KEY не определен в настройках
            Exception: Другие исключения при создании клиента (невалидные параметры и т.д.)
        """

        if not settings.MISTRAL_API_KEY:
            raise RuntimeError("MISTRAL_API_KEY not defined in .env")
        self._llm = ChatMistralAI(
            model_name=getattr(settings, "MISTRAL_MODEL", "mistral-large-latest"),
            api_key=settings.MISTRAL_API_KEY,
            temperature=0.1,
            max_tokens=1000,
        )

    async def analyze_document(self, text_content: str) -> Dict[str, Any]:
        """
        Анализирует текст документа с помощью облачной модели Mistral AI.

        Процесс:
            1. Создает промпт с помощью _create_prompt (унаследован от базового класса)
            2. Вызывает асинхронный метод ChatMistralAI.ainvoke
            3. Извлекает содержимое из объекта AIMessage (result.content)
            4. Гарантирует, что response_text является строкой
            5. Обрабатывает возможные исключения (сеть, аутентификация, API лимиты)
            6. Передает очищенный текст в _parse_response для стандартизированной обработки

        Аргументы:
            text_content (str): Текст, извлеченный из PDF документа.
                Обычно обрезается до 4000 символов в методе _create_prompt.

        Возвращает:
            Dict[str, Any]: Словарь с извлеченными полями документа:
                - document_number (str, optional): Номер документа
                - document_date (datetime, optional): Дата документа как объект datetime
                - sender (str, optional): Отправитель
                - purpose (str, optional): Назначение платежа
                - amount (Decimal, optional): Сумма как Decimal

        Исключения:
            LLMServiceError: Если Mistral API возвращает ошибку
                (аутентификация, сеть, квоты, невалидный запрос)
            DocumentAnalysisError: Если не удается распознать структуру документа (из _parse_response)
            DocumentParsingError: Если документ не содержит полезной информации (из _parse_response)

        Логирование:
            WARNING: При любых ошибках взаимодействия с Mistral API (с exc_info=False)

        Примечания:
            - Использует нативный асинхронный вызов (ainvoke)
            - Обрабатывает объекты AIMessage, извлекая text/string содержимое
            - Гарантирует строковый тип ответа перед передачей в парсер
            - Оборачивает исключения от Mistral API в LLMServiceError
            - Возвращаемые типы конвертируются в datetime и Decimal в базовом классе
        """

        prompt = self._create_prompt(text_content)

        try:
            result = await self._llm.ainvoke(prompt)
        except Exception as exc:
            logger.warning("Mistral LLM запрос завершился ошибкой (fallback): %s", exc, exc_info=False)
            raise LLMServiceError("Не удалось связаться с Mistral") from exc

        if isinstance(result, AIMessage):
            response_text = result.content
        else:
            response_text = str(result)

        if not isinstance(response_text, str):
            response_text = str(response_text)

        return self._parse_response(response_text)
