"""Общая иерархия исключений сендера (контракт §2).

Единственный источник идентичности классов для КРОСС-МОДУЛЬНЫХ except:
модули с паттерном ``try: from sender.errors import ... except: <фолбэк>``
(gates, orchestrator, personalize, suppression, validation, sender) при
наличии этого файла импортируют ОДНИ И ТЕ ЖЕ классы — иначе у каждого
модуля свой приватный фолбэк и, например, ``except PersonalizationGateError``
в orchestrator никогда не поймает исключение из personalize (найдено
тестами test_orchestrator 2026-07-18).

Модули, определяющие исключения без try-import (store, cadence, warmup,
analytics, unsub, imap_watcher), ловятся оркестратором широким Exception —
их идентичность некритична и намеренно не трогается.
"""

__all__ = [
    "SenderError",
    "ConfigError",
    "StoreError",
    "SuppressedError",
    "ValidationError",
    "PersonalizationGateError",
    "SendError",
    "RateLimitExceeded",
    "GateTrippedError",
    "YoungDomainGateError",
    "TransientError",
]


class SenderError(Exception):
    """Базовый класс всех ошибок сендера."""


class ConfigError(SenderError):
    """Невалидная схема конфига / отсутствующие секреты."""


class StoreError(SenderError):
    """Ошибка слоя хранения."""


class SuppressedError(SenderError):
    """Получатель под suppression."""


class ValidationError(SenderError):
    """Невалидный вход (адрес/токен/аргумент)."""


class PersonalizationGateError(SenderError):
    """Незаполненные {плейсхолдеры} — письмо не должно уйти (§5.4)."""


class SendError(SenderError):
    """Ошибка отправки."""


class RateLimitExceeded(SendError):
    """Превышен лимит темпа отправки."""


class GateTrippedError(SenderError):
    """Kill-switch сработал."""


class YoungDomainGateError(GateTrippedError):
    """Гейт молодых доменов: получатель на собственном корпоративном сервере,
    а домену ящика-отправителя меньше gates.young_domain.min_age_days.

    Подкласс GateTrippedError, чтобы существующие обработчики тика ловили его
    как обычный гейт; отдельное имя нужно панели — оператор должен видеть
    «домен ещё молодой, письмо подождёт», а не «репутация ящика упала»."""


class TransientError(SenderError):
    """Временная ошибка — ретраибельно."""
