"""
Модуль Pydantic схем для работы с документами.

Этот модуль определяет структуры данных для валидации, сериализации и
документирования API эндпоинтов, связанных с документами. Все схемы наследуются
от BaseModel Pydantic и поддерживают автоматическую конвертацию из/в SQLAlchemy модели.

Основные схемы:
    DocumentBase: Базовые поля документа, общие для нескольких схем
    Document: Полная схема документа для ответов API
    DocumentShort: Упрощенная схема для списков документов
    DocumentUpdate: Схема для обновления документов
    DocumentSupervisorView: Расширенная схема для просмотра руководителями

Все схемы поддерживают опциональные поля для документов, у которых AI анализ
не смог распознать некоторые данные. Десятичные суммы используют Decimal
для точного представления финансовых данных.

Зависимости:
    pydantic: BaseModel, Field для определения схем и валидации
    datetime: datetime для работы с датами
    decimal: Decimal для точного представления денежных сумм
    typing: Optional для опциональных полей
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from decimal import Decimal


class DocumentBase(BaseModel):
    """
    Базовая схема документа с общими полями.

    Содержит поля, которые извлекаются из PDF документа через AI анализ.
    Все поля опциональны, так как LLM может не распознать некоторые данные.

    Поля:
        document_number (str, optional): Номер документа.
            Пример: "12345", "INV-2024-001"
            None если не распознан.

        document_date (datetime, optional): Дата документа.
            Формат: datetime (ISO 8601 в JSON).
            None если не распознана.

        sender (str, optional): Отправитель документа.
            Пример: "ООО 'Ромашка'"
            None если не распознан.

        purpose (str, optional): Назначение платежа.
            Пример: "Оплата за поставку канцелярских товаров"
            None если не распознано.

        amount (Decimal, optional): Сумма документа.
            Точность: до 2 знаков после запятой.
            Пример: 15000.50
            None если не распознана.

    Использование:
        Используется как базовый класс для других схем документа.
    """

    document_number: Optional[str] = None
    document_date: Optional[datetime] = None
    sender: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[Decimal] = None

class Document(DocumentBase):
    """
    Полная схема документа для ответов API.

    Наследует все поля DocumentBase и добавляет системные поля.
    Используется при возврате данных о конкретном документе.

    Поля (дополнительно к DocumentBase):
        id (int): Уникальный идентификатор документа в системе.
            Обязательное поле, генерируется базой данных.

        user_id (int): Идентификатор пользователя-владельца документа.
            Обязательное поле, устанавливается автоматически при загрузке.

        created_at (datetime): Дата и время создания записи в БД.
            Формат: datetime с временной зоной.
            Устанавливается автоматически при создании.

        updated_at (datetime): Дата и время последнего обновления записи о документе.
            Формат: datetime с временной зоной.
            Устанавливается автоматически при создании и обновляется при любых изменениях.
            Позволяет отслеживать последнюю активность по документу.

        file_path (str, optional): Путь к сохраненному PDF файлу.
            None если файл не был сохранен (ошибка загрузки).

    Конфигурация:
        from_attributes = True: Позволяет создавать экземпляры схемы
            напрямую из SQLAlchemy моделей (ORM mode).

    Использование:
        - Ответ эндпоинтов загрузки документа
        - Ответ эндпоинтов получения документа по ID
        - Ответ эндпоинтов обновления документа
    """

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    file_path: Optional[str] = None

    class Config:
        from_attributes = True

class DocumentShort(BaseModel):
    """
    Упрощенная схема документа для списков.

    Содержит только наиболее важные поля для отображения в списках.
    Не включает file_path и user_id для сокращения объема данных.

    Поля:
        id (int): Уникальный идентификатор документа.

        document_number (str, optional): Номер документа.
            Field(None) эквивалентно Optional[str] = None.

        document_date (datetime, optional): Дата документа.

        sender (str, optional): Отправитель документа.

        purpose (str, optional): Назначение платежа.

        amount (Decimal, optional): Сумма документа.

        created_at (datetime): Дата создания записи.

        updated_at (datetime): Дата изменения записи.

    Конфигурация:
        from_attributes = True: Поддержка конвертации из SQLAlchemy моделей.

    Использование:
        - Ответ эндпоинтов получения списка документов пользователя
        - Используется там, где не нужны все детали документа
    """

    id: int
    document_number: Optional[str] = Field(None)
    document_date: Optional[datetime] = Field(None)
    sender: Optional[str] = Field(None)
    purpose: Optional[str] = Field(None)
    amount: Optional[Decimal] = Field(None)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    """
    Схема для обновления документа.

    Содержит только те поля, которые пользователь может редактировать.
    Все поля опциональны - поддерживается частичное обновление.

    Поля:
        document_number (str, optional): Новый номер документа.

        document_date (datetime, optional): Новая дата документа.

        sender (str, optional): Новый отправитель.

        purpose (str, optional): Новое назначение платежа.

        amount (Decimal, optional): Новая сумма.

    Конфигурация:
        from_attributes = True: Поддержка конвертации из SQLAlchemy моделей.

    Использование:
        - Тело запроса PATCH /documents/update_{document_id}
        - Валидация данных при ручном редактировании документа
    """

    document_number: Optional[str] = None
    document_date: Optional[datetime] = None
    sender: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[Decimal] = None

    class Config:
        from_attributes = True


class DocumentSupervisorView(Document):
    """
    Расширенная схема документа для просмотра руководителем.

    Наследует все поля Document и добавляет email пользователя-владельца.
    Используется для эндпоинтов, доступных только руководителям и администраторам.

    Поля (дополнительно к Document):
        user_email (str, optional): Email пользователя, загрузившего документ.
            None если пользователь не найден или удален.

    Конфигурация:
        from_attributes = True: Поддержка конвертации из SQLAlchemy моделей.
        extra = "ignore": Игнорировать дополнительные поля при валидации.

    Особенности:
        - Наследует всю валидацию и поля от Document
        - Добавляет информацию о владельце для административного просмотра
        - Игнорирует лишние поля при создании из словарей

    Использование:
        - Ответ эндпоинтов руководителя для просмотра всех документов
        - Ответ эндпоинтов руководителя для просмотра конкретного документа
    """

    user_email: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "ignore"
