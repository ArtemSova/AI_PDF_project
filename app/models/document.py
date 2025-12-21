"""
Модуль модели документа для SQLAlchemy ORM.

Этот модуль определяет модель Document, которая представляет таблицу 'documents'
в базе данных. Модель хранит информацию о загруженных PDF документах, включая
извлеченные метаданные, путь к файлу и связь с пользователем-владельцем.

Каждый документ содержит поля, извлеченные через AI анализ PDF файла,
а также служебную информацию для управления и поиска. Модель оптимизирована
для быстрого поиска документов пользователя по дате и гарантирует целостность
данных через проверочные ограничения.

Поля модели:
    id: Уникальный идентификатор документа
    document_number: Номер документа (макс. 50 символов)
    document_date: Дата документа
    sender: Отправитель документа (макс. 255 символов)
    purpose: Назначение платежа (текст без ограничения длины)
    amount: Сумма документа с точностью до 2 знаков после запятой
    file_path: Путь к сохраненному PDF файлу (макс. 500 символов)
    user_id: Идентификатор пользователя-владельца документа
    created_at: Дата и время создания записи
    updated_at: Дата и время изменения записи

Отношения:
    user: Связь с моделью User через back_populates

Индексы:
    ix_documents_user_date: Составной индекс по user_id и document_date

Ограничения:
    ck_document_amount_non_negative: Проверка неотрицательности суммы

Зависимости:
    sqlalchemy: Column, Integer, String, Numeric, DateTime, ForeignKey, Text, Index, CheckConstraint
    sqlalchemy.orm: relationship
    datetime: datetime для временных меток
    app.db.session: Base класс для SQLAlchemy моделей

Обработчики событий:
    before_update: Декоратор @event.listens_for отслеживает события обновления
        модели Document и гарантирует, что поле updated_at всегда будет установлено
        в текущее время при любом изменении записи. Это обеспечивает точное
        отслеживание последней активности даже при обновлениях, которые не
        затрагивают это поле явно.
"""

from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, Index, CheckConstraint, event
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Document(Base):
    """
    Модель документа для хранения информации о загруженных PDF файлах.

    Таблица: documents

    Каждый документ содержит как извлеченные AI метаданные, так и техническую
    информацию о файле. Модель оптимизирована для частых запросов по пользователю
    и дате документа, а также обеспечивает целостность данных через проверочные
    ограничения.

    Атрибуты:
        id (int): Первичный ключ, автоинкрементный уникальный идентификатор документа.
                  Используется для всех операций поиска и связи с другими таблицами.

        document_number (str, optional): Номер документа, извлеченный из PDF.
            Максимальная длина: 50 символов.
            Может содержать: буквы, цифры, специальные символы.
            Примеры: "12345", "INV-2024-001", "СЧФ №123".
            NULL если LLM не смог распознать номер документа.

        document_date (datetime, optional): Дата документа, извлеченная из PDF.
            Формат хранения: DateTime (YYYY-MM-DD HH:MM:SS).
            Может быть преобразована в любой формат представления.
            NULL если LLM не смог распознать дату документа.

        sender (str, optional): Наименование отправителя/юридического лица.
            Максимальная длина: 255 символов.
            Содержит: полное наименование организации или ИП.
            Пример: "ООО 'Ромашка'", "Иванов Иван Иванович (ИП)".
            NULL если LLM не смог распознать отправителя.

        purpose (str, optional): Назначение платежа или описание документа.
            Тип: Text (без ограничения длины в PostgreSQL).
            Содержит: описание товаров, услуг, основание платежа.
            Пример: "Оплата за поставку канцелярских товаров по договору №123".
            NULL если LLM не смог распознать назначение платежа.

        amount (Decimal, optional): Денежная сумма документа.
            Точность: 15 знаков всего, 2 знака после запятой.
            Диапазон: от 0.00 до 999,999,999,999.99 (неотрицательная).
            Формат: Decimal для точных финансовых расчетов.
            Проверочное ограничение гарантирует, что сумма >= 0.
            NULL если LLM не смог распознать сумму.

        file_path (str, optional): Путь к сохраненному PDF файлу на диске.
            Максимальная длина: 500 символов.
            Содержит: относительный или абсолютный путь к файлу.
            Пример: "/uploads/550e8400-e29b-41d4-a716-446655440000.pdf".
            NULL в случае, если файл не был сохранен (ошибка загрузки).

        user_id (int): Идентификатор пользователя, загрузившего документ.
            Тип: Integer, ForeignKey('users.id').
            Не может быть NULL, каждый документ должен иметь владельца.

        created_at (datetime): Дата и время создания записи в базе данных.
            По умолчанию: текущее время сервера базы данных (func.now()).
            Не может быть NULL. Не изменяется после создания.
            Формат: DateTime с временной зоной для работы в разных часовых поясах.

        updated_at (datetime): Дата и время последнего обновления записи.
            По умолчанию: текущее время сервера при создании (func.now()).
            Не может быть NULL. Автоматически обновляется при любом изменении записи.
            Формат: DateTime с временной зоной.
            Обновление происходит через триггер базы данных и обработчик событий.

    Отношения:
        user (relationship): Связь many-to-one с моделью User.
            back_populates: "documents" - явное определение обратной связи.
            Позволяет получать доступ к пользователю из документа и ко всем
            документам пользователя из объекта User.

    Индексы:
        ix_documents_user_date: Составной индекс по полям user_id и document_date.
            Оптимизирует запросы:
                - Получение документов конкретного пользователя, отсортированных по дате
                - Поиск документов пользователя за определенный период
                - Агрегатные функции по документам пользователя с группировкой по дате

    Ограничения:
        ck_document_amount_non_negative: Проверочное ограничение, гарантирующее,
            что значение поля amount всегда неотрицательно (amount >= 0).
            Защищает от ошибок ввода отрицательных сумм.


    Примечания:
        - Все текстовые поля используют кодировку UTF-8 для поддержки кириллицы
        - Для правильной работы back_populates необходимо определить обратное
          отношение в модели User: documents = relationship("Document", back_populates="user")
        - Индекс ix_documents_user_date покрывает запросы как по user_id,
          так и по комбинации user_id + document_date
        - Лучше добавить поле updated_at
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    document_number = Column(String(50), nullable=True, info={'verbose_name': 'номер_документа'})
    document_date = Column(DateTime, nullable=True, info={'verbose_name': 'дата_документа'})
    sender = Column(String(255), nullable=True, info={'verbose_name': 'отправитель'})
    purpose = Column(Text, nullable=True, info={'verbose_name': 'назначение_платежа'})
    amount = Column(Numeric(precision=15, scale=2), nullable=True, info={'verbose_name': 'сумма'})
    file_path = Column(String(500), nullable=True, info={'verbose_name': 'путь_к_файлу'})
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, info={'verbose_name': 'id_пользователя'})
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, info={'verbose_name': 'дата_создания'})
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, info={'verbose_name': 'дата_обновления'})

    user = relationship("User", back_populates='documents')

    __table_args__ = (
        # быстрый поиск по пользователю + дате
        Index("ix_documents_user_date", "user_id", "document_date"),
        # проверка на неотрицательную сумму
        CheckConstraint("amount >= 0", name="ck_document_amount_non_negative"),
    )


@event.listens_for(Document, "before_update", propagate=True)
def set_updated_at(mapper, connection, target):
    """
    Обработчик события before_update для модели Document.

    Гарантирует, что поле updated_at всегда обновляется при любом изменении
    записи документа, даже если обновление не затрагивает это поле явно.

    Аргументы:
        mapper: Маппер SQLAlchemy
        connection: Соединение с базой данных
        target: Экземпляр модели Document, который обновляется
    """

    target.updated_at = func.now()
