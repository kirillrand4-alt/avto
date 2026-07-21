"""P1: идентичность исключений/DTO во всём дереве (единые errors.py / dtos.py).

Риск, который закрывают эти тесты: приватная копия класса в модуле A делает
`except X` в модуле B бесполезным (разные объекты классов) — инвариант молча
умирает. До унификации это был РЕАЛЬНЫЙ баг: config.py кидал свой ConfigError,
cli ловил store.ConfigError -> битый конфиг ронял CLI трейсбеком.
"""

import importlib

import pytest

from sender import errors as canonical


# Модули движка, обязанные пользоваться каноническими классами.
ENGINE_MODULES = [
    "sender.analytics", "sender.auth", "sender.bitrix", "sender.cadence",
    "sender.config", "sender.gates", "sender.imap_watcher", "sender.importer",
    "sender.leaddesk", "sender.notify", "sender.orchestrator",
    "sender.personalize", "sender.postoffice", "sender.reply_classify",
    "sender.sender", "sender.store", "sender.suppression", "sender.validation",
    "sender.warmup",
]

CANON_NAMES = [
    "SenderError", "ConfigError", "StoreError", "SuppressedError",
    "ValidationError", "PersonalizationGateError", "SendError",
    "RateLimitExceeded", "GateTrippedError", "TransientError",
]


@pytest.mark.parametrize("mod_name", ENGINE_MODULES)
def test_module_exceptions_are_canonical(mod_name):
    """Каждый экспонируемый модулем канонический класс — ТОТ ЖЕ объект."""
    mod = importlib.import_module(mod_name)
    for cls_name in CANON_NAMES:
        local = getattr(mod, cls_name, None)
        if local is None:
            continue  # модуль этот класс не использует — ок
        assert local is getattr(canonical, cls_name), (
            f"{mod_name}.{cls_name} — приватная копия, а не sender.errors.{cls_name}: "
            f"except в соседнем модуле её НЕ поймает")


def test_module_specific_exceptions_subclass_canonical():
    """Модульные исключения наследуют канонический SenderError (одна иерархия)."""
    from sender.auth import AuthError
    from sender.bitrix import BitrixError
    from sender.importer import ImporterError
    from sender.notify import NotifyError
    from sender.postoffice import PostofficeError

    for exc in (AuthError, BitrixError, ImporterError, NotifyError, PostofficeError):
        assert issubclass(exc, canonical.SenderError), exc


def test_cross_module_raise_catch():
    """Смысловой инвариант: raise в personalize ловится except-ом оркестратора.

    Оба модуля обязаны ссылаться на ОДИН класс PersonalizationGateError.
    """
    from sender import orchestrator, personalize

    assert personalize.PersonalizationGateError is orchestrator.PersonalizationGateError

    def raiser():
        raise personalize.PersonalizationGateError("unfilled")

    with pytest.raises(orchestrator.PersonalizationGateError):
        raiser()


def test_dto_identity_store_dtos():
    """Обменные DTO: store реэкспортирует канонические классы из dtos."""
    from sender import dtos, store

    for name in ("RecipientIn", "CampaignIn", "SequenceStepIn", "MessageIn",
                 "EventIn", "SuppressionIn", "Recipient", "Campaign",
                 "SequenceStep", "Message", "MailboxState", "WarmupState"):
        assert getattr(store, name) is getattr(dtos, name), name

    # cadence производит MessageIn того же типа
    from sender.cadence import MessageIn as CadenceMessageIn
    assert CadenceMessageIn is dtos.MessageIn


def test_cli_catches_config_error(tmp_path, capsys):
    """Регресс найденного бага: битый конфиг -> код 1 и текст, НЕ трейсбек."""
    from sender import cli

    bad = tmp_path / "bad.yaml"
    bad.write_text("service: [нехватает: полей", encoding="utf-8")
    rc = cli.main(["--config", str(bad), "init-db"])
    assert rc == 1
    assert "Error:" in capsys.readouterr().err


def test_domain_canon_unified_across_modules():
    """P2 №4: канон домена един — стоп-лист не рассинхронится с валидацией/импортом."""
    from sender.importer import _extract_domain
    from sender.suppression import normalize_domain
    from sender.validation import Validation

    cases = ["ЗАВОД.РФ", "www.Example.COM.", "пример.рф"]
    for raw in cases:
        canon = normalize_domain(raw)
        assert Validation._norm_domain(raw) == canon, raw
        assert _extract_domain(f"user@{raw}") == canon, raw
    # мягкая семантика validation сохранена: мусор -> "" (не исключение)
    assert Validation._norm_domain("") == ""
    assert Validation._norm_domain(None) == ""
