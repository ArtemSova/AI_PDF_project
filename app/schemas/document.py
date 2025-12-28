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
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentBase(BaseModel):
    """
    Базовый класс для всех схем документов.

    Содержит основные поля, которые присутствуют в большинстве операций
    с документами. Все поля опциональны для поддержки частичного распознавания
    AI-моделью.

    Attributes:
        document_number: Номер документа (строка произвольного формата).
        document_date: Дата составления документа.
        sender: Отправитель или контрагент, указанный в документе.
        purpose: Назначение платежа или цель документа.
        amount: Денежная сумма с точностью до двух знаков после запятой.

    Note:
        Все поля могут быть None, если AI не смог их распознать в документе.
    """

    document_number: Optional[str] = None
    document_date: Optional[datetime] = None
    sender: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class Document(DocumentBase):
    """
    Полная схема документа для ответов API.

    Наследует все поля от DocumentBase и добавляет системные поля.
    Используется для отображения полной информации о документе.

    Attributes:
        id: Уникальный идентификатор документа в системе.
        user_id: Идентификатор пользователя, загрузившего документ.
        created_at: Временная метка создания записи в БД.
        updated_at: Временная метка последнего обновления записи.
        file_path: Относительный путь к файлу документа в хранилище.
                    Может быть None, если файл был удален или не загружен.

    Example:
        ```json
        {
            "id": 1,
            "user_id": 42,
            "document_number": "INV-2023-001",
            "document_date": "2023-10-15T00:00:00",
            "sender": "ООО 'Поставщик'",
            "purpose": "Оплата по договору №123",
            "amount": "15000.50",
            "created_at": "2023-10-16T10:30:00",
            "updated_at": "2023-10-16T10:30:00",
            "file_path": "/uploads/docs/invoice_1.pdf"
        }
        ```
    """

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    file_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentShort(BaseModel):
    """
    Упрощенная схема документа для использования в списках.

    Содержит только наиболее важные поля для отображения в таблицах
    и списках документов. Не включает технические поля, такие как user_id.

    Attributes:
        id: Уникальный идентификатор документа.
        document_number: Номер документа.
        document_date: Дата документа.
        sender: Отправитель документа.
        purpose: Назначение платежа.
        amount: Сумма документа.
        created_at: Дата создания записи.
        updated_at: Дата последнего обновления.

    Note:
        Все поля, кроме id, created_at и updated_at, могут быть None.
        Используется в эндпоинтах, возвращающих списки документов для
        уменьшения объема передаваемых данных.
    """

    id: int
    document_number: Optional[str] = Field(None)
    document_date: Optional[datetime] = Field(None)
    sender: Optional[str] = Field(None)
    purpose: Optional[str] = Field(None)
    amount: Optional[Decimal] = Field(None)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentUpdate(BaseModel):
    """
    Схема для обновления существующих документов.

    Используется в PATCH и PUT запросах для частичного или полного
    обновления данных документа. Все поля опциональны.

    Attributes:
        document_number: Номер документа.
        document_date: Дата документа.
        sender: Отправитель.
        purpose: Назначение платежа.
        amount: Сумма.

    Note:
        Если поле не указано в запросе, его значение остается неизменным.
        Поддерживает частичные обновления (PATCH).
    """

    document_number: Optional[str] = None
    document_date: Optional[datetime] = None
    sender: Optional[str] = None
    purpose: Optional[str] = None
    amount: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentSupervisorView(Document):
    """
    Расширенная схема документа для руководителей.

    Наследует все поля от Document и добавляет email пользователя,
    загрузившего документ. Используется в интерфейсе руководителей
    для отслеживания авторства документов.

    Attributes:
        user_email: Email пользователя, загрузившего документ.
                    Может быть None, если пользователь удален или email
                    недоступен.

    Config:
        from_attributes: Разрешает создание экземпляра из ORM объектов.
        extra: Игнорирует дополнительные поля при валидации.
    """

    user_email: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        extra="ignore",
    )
