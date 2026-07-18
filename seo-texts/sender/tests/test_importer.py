"""Юнит-тесты для sender.importer.

Тесты используют реальную временную SQLite базу через tmp_path и проверяют
потоковый импорт CSV с автодетектом формата, валидацию получателей через
мокированный Validation, и импорт списков подавления.
"""

import csv
import os
import sys
from pathlib import Path
from unittest.mock import Mock
from collections import namedtuple

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.importer import (  # noqa: E402
    import_csv,
    import_suppression,
    import_suppression_bulk,
    validate_recipients,
    ImporterError,
    _normalize_email,
    _extract_domain,
    _autodetect_column_map,
)
from sender.store import Store, RecipientIn  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402


ValidationResult = namedtuple(
    'ValidationResult',
    ['valid_status', 'provider', 'catch_all', 'role_based', 'disposable']
)


@pytest.fixture
def store(tmp_path):
    """Создаёт реальный Store на временной SQLite базе."""
    db_path = tmp_path / "test.db"
    store = Store(str(db_path))
    store.init_schema()
    return store


@pytest.fixture
def config(tmp_path):
    """Создаёт Config из BASE_YAML с подставленными паролями."""
    # Выставляем env-переменные для паролей
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = f"pass{i}"
    os.environ["UNSUB_SIGNING_SECRET"] = "secret123"
    
    config_path = tmp_path / "config.yml"
    config_path.write_text(BASE_YAML, encoding="utf-8")
    
    return Config(str(config_path))


def test_normalize_email_valid():
    """Проверяет нормализацию валидных email."""
    assert _normalize_email("Test@Example.COM") == "test@example.com"
    assert _normalize_email("  user@domain.ru  ") == "user@domain.ru"
    assert _normalize_email("admin+tag@site.co.uk") == "admin+tag@site.co.uk"


def test_normalize_email_invalid():
    """Проверяет отклонение невалидных email."""
    assert _normalize_email("") is None
    assert _normalize_email("   ") is None
    assert _normalize_email("notanemail") is None
    assert _normalize_email("@domain.com") is None
    assert _normalize_email("user@") is None
    assert _normalize_email("user@domain") is None


def test_extract_domain():
    """Проверяет извлечение домена из email."""
    assert _extract_domain("user@example.com") == "example.com"
    assert _extract_domain("admin@mail.ru") == "mail.ru"


def test_autodetect_column_map():
    """Проверяет автодетект маппинга колонок по алиасам."""
    headers = ["Email", "ИНН", "Название", "ОКВЭД"]
    mapping = _autodetect_column_map(headers)
    
    assert mapping["email"] == "Email"
    assert mapping["inn"] == "ИНН"
    assert mapping["company_name"] == "Название"
    assert mapping["okved"] == "ОКВЭД"


def test_autodetect_column_map_case_insensitive():
    """Проверяет регистронезависимость автодетекта."""
    headers = ["EMAIL", "инн", "Организация"]
    mapping = _autodetect_column_map(headers)
    
    assert mapping["email"] == "EMAIL"
    assert mapping["inn"] == "инн"
    assert mapping["company_name"] == "Организация"


def test_import_csv_basic(store, tmp_path):
    """Проверяет базовый импорт CSV с точкой-с-запятой."""
    csv_path = tmp_path / "recipients.csv"
    csv_path.write_text(
        "Email;ИНН;Название;ОКВЭД\n"
        "user1@example.com;1234567890;ООО Пример;62.01\n"
        "user2@test.ru;0987654321;ИП Тестов;47.91\n",
        encoding="utf-8-sig"
    )
    
    stats = import_csv(store, str(csv_path))
    
    assert stats["total_rows"] == 2
    assert stats["imported"] == 2
    assert stats["skipped_invalid"] == 0
    assert stats["duplicates_in_file"] == 0
    
    # Проверяем что записи в БД
    recipients = list(store.iter_recipients())
    assert len(recipients) == 2
    
    emails = {r.email for r in recipients}
    assert "user1@example.com" in emails
    assert "user2@test.ru" in emails


def test_import_csv_cp1251(store, tmp_path):
    """Проверяет импорт CSV в кодировке cp1251."""
    csv_path = tmp_path / "recipients_cp1251.csv"
    csv_path.write_text(
        "Email;ИНН;Название\n"
        "admin@example.ru;1111111111;Компания Тест\n",
        encoding="cp1251"
    )
    
    stats = import_csv(store, str(csv_path))
    
    assert stats["total_rows"] == 1
    assert stats["imported"] == 1
    
    recipients = list(store.iter_recipients())
    assert len(recipients) == 1
    assert recipients[0].email == "admin@example.ru"
    assert recipients[0].company_name == "Компания Тест"


def test_import_csv_invalid_emails(store, tmp_path):
    """Проверяет счётчик skipped_invalid для мусорных email."""
    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(
        "Email;ИНН\n"
        "valid@test.com;1111\n"
        "notanemail;2222\n"
        "@invalid.com;3333\n"
        "another@valid.ru;4444\n",
        encoding="utf-8"
    )
    
    stats = import_csv(store, str(csv_path))
    
    assert stats["total_rows"] == 4
    assert stats["imported"] == 2
    assert stats["skipped_invalid"] == 2
    
    recipients = list(store.iter_recipients())
    assert len(recipients) == 2


def test_import_csv_duplicates_in_file(store, tmp_path):
    """Проверяет обнаружение дубликатов внутри файла."""
    csv_path = tmp_path / "duplicates.csv"
    csv_path.write_text(
        "Email;Название\n"
        "user@example.com;Первая\n"
        "admin@test.ru;Вторая\n"
        "user@example.com;Дубль\n",
        encoding="utf-8"
    )
    
    stats = import_csv(store, str(csv_path))
    
    assert stats["total_rows"] == 3
    assert stats["duplicates_in_file"] == 1
    # В БД всё равно одна запись благодаря upsert
    recipients = list(store.iter_recipients())
    assert len(recipients) == 2


def test_import_csv_manual_column_map(store, tmp_path):
    """Проверяет что переданный column_map переопределяет автодетект."""
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text(
        "EmailAddr;TaxID;Org\n"
        "user@example.com;1234567890;ООО Тест\n",
        encoding="utf-8"
    )
    
    column_map = {
        "email": "EmailAddr",
        "inn": "TaxID",
        "company_name": "Org"
    }
    
    stats = import_csv(store, str(csv_path), column_map=column_map)
    
    assert stats["total_rows"] == 1
    assert stats["imported"] == 1
    
    recipients = list(store.iter_recipients())
    assert recipients[0].email == "user@example.com"
    assert recipients[0].inn == "1234567890"
    assert recipients[0].company_name == "ООО Тест"


def test_import_csv_missing_email_column(store, tmp_path):
    """Проверяет ImporterError если email-колонка не найдена."""
    csv_path = tmp_path / "no_email.csv"
    csv_path.write_text(
        "Name;Phone\n"
        "Иванов;+79991234567\n",
        encoding="utf-8"
    )
    
    with pytest.raises(ImporterError, match="Обязательная колонка 'email' не найдена"):
        import_csv(store, str(csv_path))


def test_import_csv_limit(store, tmp_path):
    """Проверяет что limit ограничивает чтение."""
    csv_path = tmp_path / "many.csv"
    csv_path.write_text(
        "Email\n"
        "user1@example.com\n"
        "user2@example.com\n"
        "user3@example.com\n"
        "user4@example.com\n",
        encoding="utf-8"
    )
    
    stats = import_csv(store, str(csv_path), limit=2)
    
    assert stats["total_rows"] == 2
    assert stats["imported"] == 2


def test_import_csv_progress_callback(store, tmp_path):
    """Проверяет что progress_cb вызывается."""
    csv_path = tmp_path / "progress.csv"
    lines = ["Email\n"]
    for i in range(15000):
        lines.append(f"user{i}@example.com\n")
    csv_path.write_text("".join(lines), encoding="utf-8")
    
    calls = []
    
    def progress_cb(count):
        calls.append(count)
    
    import_csv(store, str(csv_path), progress_cb=progress_cb)
    
    # Должно быть вызвано на 10000 и финальном счёте
    assert 10000 in calls
    assert calls[-1] == 15000


def test_import_csv_batch_size(store, tmp_path):
    """Проверяет что batch_size работает корректно."""
    csv_path = tmp_path / "batch.csv"
    lines = ["Email\n"]
    for i in range(2500):
        lines.append(f"user{i}@example.com\n")
    csv_path.write_text("".join(lines), encoding="utf-8")
    
    stats = import_csv(store, str(csv_path), batch_size=500)
    
    assert stats["total_rows"] == 2500
    assert stats["imported"] == 2500
    
    recipients = list(store.iter_recipients())
    assert len(recipients) == 2500


def test_import_csv_file_not_found(store, tmp_path):
    """Проверяет ImporterError если файл не существует."""
    with pytest.raises(ImporterError, match="Файл не найден"):
        import_csv(store, str(tmp_path / "nonexistent.csv"))
