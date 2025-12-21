"""
Модуль асинхронной отправки email уведомлений.

Этот модуль предоставляет функции для отправки HTML и plain-text писем через SMTP с SSL/TLS.
Поддерживает два типа уведомлений:
1. Подтверждение регистрации нового пользователя
2. Сброс пароля учетной записи

Все операции выполняются асинхронно с использованием aiosmtplib и логируются.
Письма отправляются с поддержкой как plain-text, так и HTML формата для лучшей совместимости.

Основные функции:
    send_registration_email: Отправка письма подтверждения регистрации
    send_password_reset_email: Отправка письма для сброса пароля

Вспомогательные функции (приватные):
    _make_link: Формирование ссылки с токеном
    _format_template: Заполнение шаблонов данными
    _make_message: Создание объекта EmailMessage
    _tls_context: Создание SSL контекста для безопасного соединения
    _smtp_send: Асинхронная отправка через SMTP

Зависимости:
    aiosmtplib: Асинхронная отправка email через SMTP
    ssl: Создание безопасного TLS соединения
    email.message: EmailMessage для формирования писем
    logging: Логирование операций
    app.core.config: Настройки email сервера
"""

import logging
import ssl
from email.message import EmailMessage
from typing import Mapping, Tuple

import aiosmtplib
from app.core.config import settings

log = logging.getLogger(__name__)


# 1 Текстовые шаблоны
REG_SUBJECT = "Подтверждение регистрации AI_PDF"
REG_PLAIN = """\
Здравствуйте!

Вы (или кто‑то) зарегистрировали аккаунт с этим email на AI_PDF.
Чтобы подтвердить регистрацию, перейдите по ссылке ниже:

{link}

С уважением,
{sender}
"""
REG_HTML = """\
<html>
  <body>
    <p>Здравствуйте!<br><br>
       Вы (или кто‑то) зарегистрировали аккаунт с этим email на <b>AI_PDF</b>.<br><br>
       Чтобы подтвердить регистрацию, <a href="{link}">нажмите здесь</a>.<br><br>
       Если вы не регистрировались — проигнорируйте это письмо.<br><br>
       С уважением,<br>
       {sender}
    </p>
  </body>
</html>
"""

RESET_SUBJECT = "Сброс пароля на AI_PDF"
RESET_PLAIN = """\
Здравствуйте!

Вы запросили сброс пароля для аккаунта {email}.
Перейдите по ссылке ниже, чтобы задать новый пароль (ссылка действует 30 минут):

{link}

Если вы не делали запрос – просто проигнорируйте это письмо.

С уважением,
{sender}
"""
RESET_HTML = """\
<html>
  <body>
    <p>Здравствуйте!<br><br>
       Вы запросили сброс пароля для аккаунта <b>{email}</b>.<br><br>
       Чтобы задать новый пароль, <a href="{link}">нажмите здесь</a>.
       Ссылка действует 30 минут.<br><br>
       Если запрос не делали — проигнорируйте письмо.<br><br>
       С уважением,<br>
       {sender}
    </p>
  </body>
</html>
"""


# 2 Вспомогательные функции (общие для всех писем, можно вынести в отдельный файл)
def _make_link(base: str, token: str) -> str:
    """
    Формирование ссылки с токеном для подтверждения или сброса пароля.

    Процесс:
        1. Удаление завершающего слеша из базового URL
        2. Добавление токена в качестве параметра запроса

    Аргументы:
        base (str): Базовый URL (например, https://example.com/confirm)
        token (str): JWT токен для включения в ссылку

    Возвращает:
        str: Полная ссылка вида https://example.com/confirm?token=токен
    """

    base = base.rstrip("/")
    return f"{base}/?token={token}"


def _format_template(
    plain_template: str,
    html_template: str,
    placeholders: Mapping[str, str],
) -> Tuple[str, str]:
    """
    Заполнение шаблонов письма данными.

    Процесс:
        1. Замена плейсхолдеров в plain-text шаблоне
        2. Замена плейсхолдеров в HTML шаблоне
        3. Возврат обоих версий письма

    Аргументы:
        plain_template (str): Шаблон plain-text версии письма
        html_template (str): Шаблон HTML версии письма
        placeholders (Mapping[str, str]): Словарь значений для замены плейсхолдеров

    Возвращает:
        Tuple[str, str]: Кортеж из (plain_text, html_text) заполненных шаблонов
    """

    plain = plain_template.format(**placeholders)
    html = html_template.format(**placeholders)
    return plain, html


def _make_message(to: str, subject: str, plain: str, html: str) -> EmailMessage:
    """
    Заполнение шаблонов письма данными.

    Процесс:
        1. Замена плейсхолдеров в plain-text шаблоне
        2. Замена плейсхолдеров в HTML шаблоне
        3. Возврат обоих версий письма

    Аргументы:
        plain_template (str): Шаблон plain-text версии письма
        html_template (str): Шаблон HTML версии письма
        placeholders (Mapping[str, str]): Словарь значений для замены плейсхолдеров

    Возвращает:
        Tuple[str, str]: Кортеж из (plain_text, html_text) заполненных шаблонов
    """

    msg = EmailMessage()
    msg["From"] = f"{settings.EMAIL_SENDER_NAME} <{settings.EMAIL_HOST_USER}>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")
    return msg


def _tls_context() -> ssl.SSLContext:
    """
    Создание SSL/TLS контекста для безопасного соединения с SMTP сервером.

    Процесс:
        1. Создание контекста с настройками по умолчанию
        2. Включение проверки имени хоста
        3. Требование сертификата от сервера

    Возвращает:
        ssl.SSLContext: Настроенный SSL контекст для SMTP соединения
    """

    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


async def _smtp_send(msg: EmailMessage) -> None:
    """
    Асинхронная отправка письма через SMTP сервер.

    Процесс:
        1. Получение настроек SMTP из конфигурации приложения
        2. Установка соединения с SMTP сервером
        3. Аутентификация с использованием логина и пароля
        4. Отправка письма через aiosmtplib
        5. Установка таймаута 20 секунд для операции

    Аргументы:
        msg (EmailMessage): Сформированное письмо для отправки

    Исключения:
        SMTPException: При ошибках соединения или отправки
        TimeoutError: При превышении таймаута 20 секунд

    Примечание:
        Использует настройки EMAIL_USE_SSL для определения типа соединения.
        Если EMAIL_USE_SSL=True, используется TLS поверх SSL.
    """

    await aiosmtplib.send(
        msg,
        hostname=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_SSL,
        tls_context=_tls_context(),
        timeout=20,
    )


# 3 Публичные функции
async def send_registration_email(to_email: str, token: str) -> bool:
    """
    Отправка письма с подтверждением регистрации нового пользователя.

    Процесс:
        1. Формирование ссылки с токеном подтверждения
        2. Заполнение шаблонов письма данными (ссылка, имя отправителя)
        3. Создание объекта EmailMessage
        4. Отправка через SMTP сервер
        5. Логирование результата операции

    Аргументы:
        to_email (str): Email адрес получателя (нового пользователя)
        token (str): JWT токен для подтверждения регистрации

    Возвращает:
        bool: True если письмо отправлено успешно, False в случае ошибки

    Логирование:
        INFO: При успешной отправке письма
        ERROR: При ошибке отправки с деталями исключения
    """

    link = _make_link(settings.CONFIRM_BASE_URL, token)

    placeholders = {"link": link, "sender": settings.EMAIL_SENDER_NAME}
    plain, html = _format_template(REG_PLAIN, REG_HTML, placeholders)

    msg = _make_message(to_email, REG_SUBJECT, plain, html)

    try:
        await _smtp_send(msg)
        log.info("Отправлено письмо регистрации для %s", to_email)
        return True
    except Exception as exc:  # noqa: BLE001
        log.exception("Не удалось отправить письмо регистрации: %s", exc)
        return False


async def send_password_reset_email(to_email: str, token: str) -> bool:
    """
    Отправка письма со ссылкой для сброса пароля.

    Процесс:
        1. Проверка наличия RESET_BASE_URL в настройках
        2. Формирование ссылки с токеном сброса пароля
        3. Заполнение шаблонов письма данными (email, ссылка, имя отправителя)
        4. Создание объекта EmailMessage
        5. Отправка через SMTP сервер
        6. Логирование результата операции

    Аргументы:
        to_email (str): Email адрес получателя (пользователя, запросившего сброс)
        token (str): JWT токен для сброса пароля

    Возвращает:
        bool: True если письмо отправлено успешно, False в случае ошибки

    Исключения:
        RuntimeError: Если RESET_BASE_URL не задан в настройках (.env файл)

    Логирование:
        INFO: При успешной отправке письма
        ERROR: При ошибке отправки с деталями исключения
    """

    base = getattr(settings, "RESET_BASE_URL", None)
    if not base:
        raise RuntimeError("RESET_BASE_URL не задан в .env")

    link = _make_link(base, token)

    placeholders = {
        "email": to_email,
        "link": link,
        "sender": settings.EMAIL_SENDER_NAME,
    }
    plain, html = _format_template(RESET_PLAIN, RESET_HTML, placeholders)

    msg = _make_message(to_email, RESET_SUBJECT, plain, html)

    try:
        await _smtp_send(msg)
        log.info("Отправлено письмо сброса пароля для %s", to_email)
        return True
    except Exception as exc:  # noqa: BLE001
        log.exception("Не удалось отправить письмо сброса пароля: %s", exc)
        return False
