"""
LangGraph-анализатор PDF документов с автоматическим fallback-переключением.

Этот модуль реализует анализатор PDF документов, использующий граф состояний LangGraph
для реализации стратегии автоматического переключения между различными AI моделями.
Основная цель - повышение отказоустойчивости системы при обработке документов.

Архитектура:
    LangGraphPDFAnalyzer: Основной класс, реализующий паттерн "Circuit Breaker" для
    автоматического переключения между локальной (Ollama) и облачной (Mistral) моделями
    в случае сбоев одной из них.

Стратегия обработки:
    1. Первичная попытка: Локальная модель Ollama (быстрая, без интернет-соединения)
    2. Fallback: Облачная модель Mistral AI (используется при ошибках Ollama)
    3. Финальный результат: Возврат успешного анализа или ошибки о недоступности

Граф состояний (LangGraph):
    start → ollama_node → (success) → final_node → result
                     ↓ (fallback)
                   mistral_node → final_node → result

Ключевые особенности:
    - Автоматическое переключение при сбоях без прерывания процесса
    - Сохранение контекста ошибок для логирования и отладки
    - Оптимизация использования ресурсов (создание клиентов один раз)
    - Гибкая маршрутизация на основе состояния анализа

Типы обрабатываемых ошибок:
    DocumentParsingError: Документ не распознан (не обрабатывается, пробрасывается выше)
    LLMServiceError: Ошибка соединения с AI сервисом (запускает fallback)
    Exception: Любые другие ошибки (запускают fallback)

Зависимости:
    logging: Логирование работы анализатора и ошибок
    typing: Аннотации типов для TypeDict и опциональных полей
    langgraph.graph: StateGraph для построения графа состояний
    app.services.pdf_analyzer_base: Базовый класс PDFAnalyzerBase
    app.services.pdf_llm_analyzer: Конкретные реализации анализаторов
    app.utils.exceptions: Пользовательские исключения

Использование:
    Рекомендуется для производственных сред, где требуется высокая доступность
    и отказоустойчивость при обработке документов. Поддерживается настройкой
    USE_LANGGRAPH_FALLBACK в конфигурации приложения.
"""

import logging
from typing import Any, Dict, TypedDict, Optional
from langgraph.graph import StateGraph

from app.services.pdf_analyzer_base import PDFAnalyzerBase
from app.services.pdf_llm_analyzer import PDFLLMAnalyzer, PDFMistralAnalyzer
from app.utils.exceptions import DocumentParsingError, LLMServiceError


logger = logging.getLogger(__name__)


class AnalyzerState(TypedDict, total=False):
    """
    Типизированный словарь состояния для передачи данных между узлами графа LangGraph.

    Определяет структуру данных, которая передается по графу обработки документа.
    Использует total=False для поддержки частичного заполнения полей.

    Атрибуты:
        text (str): Исходный текст PDF документа, полученный от DocumentProcessor.
            Должен быть непустой строкой с максимальной длиной 4000 символов.
        result (Optional[Dict]): Успешно распарсенный результат от AI модели.
            Содержит структурированные данные документа в формате, определенном
            базовым классом PDFAnalyzerBase. None если анализ еще не выполнен.
        error (Optional[str]): Сообщение об ошибке, если вызов AI модели завершился неудачно.
            Содержит описание ошибки для логирования и отладки.
        fallback_needed (bool, default=False): Флаг необходимости перехода к резервной модели.
            Устанавливается в True при ошибках Ollama, что запускает переход к Mistral.

    Пример заполненного состояния:
        {
            "text": "Счет №123 от 2024-01-15...",
            "result": {
                "document_number": "123",
                "document_date": "2024-01-15T00:00:00",
                "sender": "ООО Поставщик",
                "purpose": "Оплата товаров",
                "amount": 15000.00
            },
            "error": None,
            "fallback_needed": False
        }

    Примечания:
        - Поле `result` может быть частично заполнено (не все поля извлечены)
        - Поле `error` используется только при сбоях AI моделей, не при парсинге
        - Поле `fallback_needed` является ключевым для маршрутизации графа
    """

    text: str                     # исходный текст PDF
    result: Optional[Dict]        # успешно распаршенный результат
    error: Optional[str]         # сообщение об ошибке сервиса
    fallback_needed: bool = False


class LangGraphPDFAnalyzer(PDFAnalyzerBase):
    """
    Анализатор PDF документов с графом состояний для автоматического fallback-переключения.

    Реализует стратегию "Circuit Breaker" для обработки документов:
    1. Первичная обработка через локальную модель Ollama
    2. Автоматическое переключение на Mistral при ошибках Ollama
    3. Возврат результата или финальной ошибки при недоступности обеих моделей

    Особенности реализации:
        - Наследует PDFAnalyzerBase, обеспечивая совместимость с DocumentProcessor
        - Использует LangGraph для управления потоком выполнения
        - Создает экземпляры анализаторов один раз для оптимизации ресурсов
        - Компилирует граф при инициализации для быстрого выполнения

    Атрибуты:
        _ollama (PDFLLMAnalyzer): Экземпляр анализатора для локальной модели Ollama.
            Используется для первичной попытки анализа.
        _mistral (PDFMistralAnalyzer): Экземпляр анализатора для облачной модели Mistral.
            Используется как резервный вариант при ошибках Ollama.
        _graph (StateGraph): Построенный граф состояний с узлами и переходами.
        _app (CompiledGraph): Скомпилированное приложение графа для выполнения.

    Пример использования:
        from app.services.langgraph_fallback_analyzer import LangGraphPDFAnalyzer

        async def process_document(text: str):
            analyzer = LangGraphPDFAnalyzer()
            try:
                result = await analyzer.analyze_document(text)
                return result
            except LLMServiceError as e:
                # Обе модели недоступны
                logger.error(f"Анализ невозможен: {e}")
                raise

    Примечания:
        - Требует наличия настроек для обеих моделей (Ollama и Mistral)
        - Исключение DocumentParsingError пробрасывается сразу (не запускает fallback)
        - Все ошибки соединения логируются с деталями для отладки
    """

    def __init__(self) -> None:
        """
        Инициализирует анализатор и строит граф обработки.

        Процесс инициализации:
            1. Создание экземпляров анализаторов Ollama и Mistral
            2. Построение структуры графа с узлами и переходами
            3. Компиляция графа для оптимального выполнения

        Анализторы создаются один раз при инициализации для:
            - Избежания повторного создания соединений
            - Сокращения накладных расходов на каждый вызов
            - Оптимизации использования памяти

        Исключения:
            RuntimeError: При невозможности создать клиентов анализаторов
            ImportError: При отсутствии зависимостей LangGraph

        Логирование:
            DEBUG: Информация о создании анализаторов и компиляции графа
        """

        # Создаём “тяжёлые” клиенты один раз – экономим лишние подключения.
        self._ollama = PDFLLMAnalyzer()
        self._mistral = PDFMistralAnalyzer()

        # Строим граф один раз на старте инстанса.
        self._graph = self._build_graph()
        self._app = self._graph.compile()

    #   Методы‑узлы графа
    async def _ollama_node(self, state: AnalyzerState) -> AnalyzerState:
        """
        Узел графа для анализа документа через локальную модель Ollama.

        Выполняет первичную попытку извлечения информации из документа.
        В случае ошибок соединения или выполнения устанавливает флаг fallback_needed.

        Аргументы:
            state (AnalyzerState): Текущее состояние графа, должно содержать поле "text".

        Возвращает:
            AnalyzerState: Обновленное состояние с одним из вариантов:
                - result: Успешно распарсенные данные документа
                - error: Сообщение об ошибке (при сбоях)
                - fallback_needed: True при ошибках, требующих переключения

        Исключения:
            DocumentParsingError: Пробрасывается выше, если документ не распознан.
                Не приводит к fallback, так как проблема в содержимом документа.

        Логирование:
            DEBUG: Информация о вызове Ollama
            WARNING: Предупреждения о недоступности Ollama с деталями ошибки

        Обработка ошибок:
            1. DocumentParsingError: Документ не распознан - пробрасывается выше
            2. LLMServiceError: Ошибка сервиса Ollama - запускает fallback
            3. Exception: Любая другая ошибка - запускает fallback
        """

        try:
            logger.debug("Вызов Ollama‑LLM")
            result = await self._ollama.analyze_document(state["text"])
            return {"result": result, "fallback_needed": False}
        except DocumentParsingError:
            raise                       # Документ не распознан – сразу возвращаем клиенту
        except LLMServiceError as exc:
            logger.warning("Ollama недоступна (%s). Переходим к Mistral.", exc)
            return {"result": None, "error": str(exc), "fallback_needed": True}
        except Exception as exc:
            logger.warning("Неожиданная ошибка Ollama: %s", exc, exc_info=False)
            return {"result": None, "error": str(exc), "fallback_needed": True}


    async def _mistral_node(self, state: AnalyzerState) -> AnalyzerState:
        """
        Узел графа для резервного анализа через облачную модель Mistral AI.

        Вызывается только при неудачной попытке анализа через Ollama.
        Является последним узлом анализа документа.

        Аргументы:
            state (AnalyzerState): Текущее состояние графа, должно содержать поле "text".

        Возвращает:
            AnalyzerState: Обновленное состояние с результатом или ошибкой.

        Исключения:
            DocumentParsingError: Пробрасывается выше, если документ не распознан.

        Логирование:
            DEBUG: Информация о вызове Mistral
            WARNING: Предупреждения о недоступности Mistral
            ERROR: Неожиданные ошибки Mistral с полным стектрейсом

        Особенности:
            - Не устанавливает fallback_needed=True, так как это последний узел
            - Все ошибки кроме DocumentParsingError приводят к финальной ошибке
        """

        try:
            logger.debug("Вызов Mistral‑LLM")
            result = await self._mistral.analyze_document(state["text"])
            return {"result": result, "fallback_needed": False}
        except DocumentParsingError:
            raise
        except LLMServiceError as exc:
            logger.warning("Mistral недоступен (%s). Окончательный отказ.", exc)
            return {"result": None, "error": str(exc), "fallback_needed": True}
        except Exception as exc:  # noqa: BLE001
            logger.error("Неожиданная ошибка Mistral: %s", exc, exc_info=False)
            return {"result": None, "error": str(exc), "fallback_needed": True}


    async def _final_node(self, state: AnalyzerState) -> AnalyzerState:
        """
        Финальный узел графа для возврата результата или генерации ошибки.

        Определяет итоговый результат обработки документа на основе состояния.
        Выбрасывает исключение если обе модели оказались недоступны.

        Аргументы:
            state (AnalyzerState): Текущее состояние графа после всех обработок.

        Возвращает:
            AnalyzerState: Состояние только с полем "result" (очищенное от вспомогательных полей).

        Исключения:
            LLMServiceError: Выбрасывается если ни одна модель не вернула результат.
                Сообщение указывает на недоступность обоих сервисов.

        Логика:
            1. Если есть result - возвращает его
            2. Если result отсутствует - генерирует финальную ошибку
            3. Очищает состояние от временных полей (error, fallback_needed)
        """

        if state.get("result") is not None:
            return {"result": state["result"]}
        raise LLMServiceError("Оба LLM‑сервиса недоступны. Попробуйте позже.")

    #   Построение графа
    def _build_graph(self) -> StateGraph:
        """
        Строит и конфигурирует граф состояний LangGraph для обработки документов.

        Создает структуру графа с узлами и условными переходами:
          - Начальный узел: ollama
          - Условный переход: на основе fallback_needed
          - Резервный узел: mistral (при необходимости)
          - Финальный узел: final

        Структура графа:
            ollama → (если fallback_needed=False) → final
                     (если fallback_needed=True)  → mistral → final

        Возвращает:
            StateGraph: Настроенный, но еще не скомпилированный граф.

        Компоненты графа:
            - Узлы: ollama, mistral, final
            - Условные ребра: Из ollama в final или mistral
            - Прямые ребра: Из mistral в final

        Маршрутизация:
            Функция _route_from_ollama анализирует состояние после выполнения
            узла ollama и определяет следующий узел на основе fallback_needed.

        Примеры маршрутов:
            1. Успешный Ollama: ollama → final
            2. Fallback: ollama → mistral → final
        """

        graph = StateGraph(AnalyzerState)

        # Узлы
        graph.add_node("ollama", self._ollama_node)
        graph.add_node("mistral", self._mistral_node)
        graph.add_node("final", self._final_node)

        # Точка входа
        graph.set_entry_point("ollama")

        # Переход из Ollama
        def _route_from_ollama(state: AnalyzerState) -> str:
            """
            Условная функция маршрутизации после выполнения узла Ollama.

            Анализирует состояние на наличие флага fallback_needed.
            Определяет, нужно ли переходить к резервной модели Mistral.

            Аргументы:
                state (AnalyzerState): Состояние после выполнения узла ollama.

            Возвращает:
                str: Имя следующего узла:
                    - "final": Если анализ успешен (fallback_needed=False)
                    - "mistral": Если требуется fallback (fallback_needed=True)

            Логика:
                Проверяет значение fallback_needed в состоянии.
                True означает, что Ollama не смог обработать документ из-за ошибок сервиса.
            """

            return "mistral" if state.get("fallback_needed") else "final"

        graph.add_conditional_edges(
            "ollama",
            _route_from_ollama,
            ["final", "mistral"],
        )

        # После Mistral всегда идём в финал (независимо от ошибки)
        graph.add_edge("mistral", "final")

        return graph


    async def analyze_document(self, text_content: str) -> Dict[str, Any]:
        """
        Основной метод анализа документа, реализующий интерфейс PDFAnalyzerBase.

        Запускает скомпилированный граф обработки с переданным текстом документа.
        Обрабатывает результат выполнения графа и возвращает структурированные данные.

        Аргументы:
            text_content (str): Текст PDF документа для анализа.
                Обычно обрезается до 4000 символов для экономии токенов.
                Должен быть непустой строкой с текстом, извлеченным из PDF.

        Возвращает:
            Dict[str, Any]: Словарь с извлеченными полями документа:
                - document_number (str, optional): Номер документа
                - document_date (datetime, optional): Дата документа как datetime
                - sender (str, optional): Отправитель документа
                - purpose (str, optional): Назначение платежа
                - amount (Decimal, optional): Сумма документа как Decimal

        Исключения:
            LLMServiceError: Если оба AI сервиса недоступны
            DocumentParsingError: Если документ не содержит полезной информации
            DocumentAnalysisError: При других ошибках анализа
            RuntimeError: При ошибках выполнения графа

        Процесс выполнения:
            1. Инициализация состояния с текстом документа
            2. Запуск графа методом ainvoke()
            3. Извлечение результата из финального состояния
            4. Возврат структурированных данных

        Примечания:
            - Использует предварительно скомпилированный граф для скорости
            - Все исключения от узлов графа пробрасываются выше
            - Логирует детали выполнения на уровне DEBUG
        """

        result_state: AnalyzerState = await self._app.ainvoke({"text": text_content})
        return result_state["result"]
