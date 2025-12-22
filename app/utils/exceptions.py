class DocumentAnalysisError(Exception):
    """Исключение для ошибок анализа документов"""
    pass

class DocumentParsingError(DocumentAnalysisError):
    """
    Ошибка разбора уже полученного ответа LLM.
    Возникает, когда JSON‑структура корректна, но обязательные поля
    (номер, дата, отправитель, назначение, сумма) отсутствуют или равны null.
    """
    pass


class LLMServiceError(DocumentAnalysisError):
    """
    Ошибка обращения к LLM‑сервису (тайм‑аут, отсутствие подключения,
    неверный API‑ключ и т.п.). Используется для переключения на fallback.
    """
    pass
