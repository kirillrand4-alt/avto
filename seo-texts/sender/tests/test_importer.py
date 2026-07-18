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


def test_import_suppression_inn(store, tmp_path):
    """Проверяет импорт списка ИНН для подавления."""
    supp_path = tmp_path / "competitors_inn.txt"
    supp_path.write_text(
        "# Конкуренты по ИНН\n"
        "1234567890\n"
        "0987654321\n"
        "\n"
        "# Ещё один\n"
        "1111111111\n",
        encoding="utf-8"
    )
    
    added = import_suppression(store, str(supp_path), scope="inn", reason="competitor")
    
    assert added == 3
    
    # Проверяем что записи в suppression
    from sender.suppression import Suppression
    suppression = Suppression(store)
    
    assert suppression.is_suppressed_inn("1234567890")
    assert suppression.is_suppressed_inn("0987654321")
    assert suppression.is_suppressed_inn("1111111111")


def test_import_suppression_domain(store, tmp_path):
    """Проверяет импорт списка доменов для подавления."""
    supp_path = tmp_path / "competitors_domain.txt"
    supp_path.write_text(
        "competitor.com\n"
        "RIVAL.RU\n"
        "# Комментарий\n"
        "another-competitor.net\n",
        encoding="utf-8"
    )
    
    added = import_suppression(store, str(supp_path), scope="domain", reason="competitor")
    
    assert added == 3
    
    from sender.suppression import Suppression
    suppression = Suppression(store)
    
    assert suppression.is_suppressed_domain("competitor.com")
    assert suppression.is_suppressed_domain("rival.ru")  # нормализация
    assert suppression.is_suppressed_domain("another-competitor.net")


def test_import_suppression_idempotent(store, tmp_path):
    """Проверяет идемпотентность повторного импорта."""
    supp_path = tmp_path / "idempotent.txt"
    supp_path.write_text(
        "1234567890\n"
        "0987654321\n",
        encoding="utf-8"
    )
    
    added1 = import_suppression(store, str(supp_path), scope="inn")
    assert added1 == 2
    
    # Повторный импорт
    added2 = import_suppression(store, str(supp_path), scope="inn")
    assert added2 == 0  # Дубликаты не добавляются


def test_import_suppression_invalid_scope(store, tmp_path):
    """Проверяет ImporterError при неверном scope."""
    supp_path = tmp_path / "test.txt"
    supp_path.write_text("value\n", encoding="utf-8")
    
    with pytest.raises(ImporterError, match="Неверный scope"):
        import_suppression(store, str(supp_path), scope="invalid")


def test_import_suppression_file_not_found(store, tmp_path):
    """Проверяет ImporterError если файл подавления не найден."""
    with pytest.raises(ImporterError, match="Файл не найден"):
        import_suppression(store, str(tmp_path / "missing.txt"), scope="inn")


def test_import_suppression_bulk(store, tmp_path):
    """Проверяет массовый импорт через import_suppression_bulk."""
    supp_path = tmp_path / "bulk.txt"
    lines = []
    for i in range(2500):
        lines.append(f"123456789{i:04d}\n")
    supp_path.write_text("".join(lines), encoding="utf-8")
    
    added = import_suppression_bulk(store, str(supp_path), scope="inn", batch_size=500)
    
    assert added == 2500


def test_validate_recipients_basic(store, config, monkeypatch):
    """Проверяет базовую валидацию получателей через мокированный Validation."""
    # Добавляем получателей
    store.bulk_upsert_recipients([
        RecipientIn(email="valid@example.com", domain="example.com"),
        RecipientIn(email="invalid@test.com", domain="test.com"),
        RecipientIn(email="risky@mail.ru", domain="mail.ru"),
    ])
    
    # Мокируем Validation
    mock_validation = Mock()
    
    def mock_validate_batch(emails):
        results = []
        for email in emails:
            if email == "valid@example.com":
                results.append(ValidationResult("valid", "google", False, False, False))
            elif email == "invalid@test.com":
                results.append(ValidationResult("invalid", None, None, None, None))
            else:
                results.append(ValidationResult("risky", "mail.ru", True, False, False))
        return results
    
    mock_validation.validate_batch = mock_validate_batch
    
    # Патчим класс Validation
    from sender import importer
    monkeypatch.setattr(importer, "Validation", lambda cfg: mock_validation)
    
    stats = validate_recipients(store, config)
    
    assert stats["total"] == 3
    assert stats["valid"] == 1
    assert stats["invalid"] == 1
    assert stats["risky"] == 1
    
    # Проверяем что статусы записаны
    recipients = {r.email: r for r in store.iter_recipients()}
    assert recipients["valid@example.com"].valid_status == "valid"
    assert recipients["invalid@test.com"].valid_status == "invalid"
    assert recipients["risky@mail.ru"].valid_status == "risky"


def test_validate_recipients_only_unknown(store, config, monkeypatch):
    """Проверяет что only_unknown не перевалидирует уже валидированных."""
    # Добавляем получателей с разными статусами
    r1_id = store.bulk_upsert_recipients([
        RecipientIn(email="already@valid.com", domain="valid.com")
    ])[0]
    r2_id = store.bulk_upsert_recipients([
        RecipientIn(email="unknown@test.com", domain="test.com")
    ])[0]
    
    # Помечаем первого как уже валидного
    store.set_recipient_validation(r1_id, valid_status="valid", mx_provider="google")
    
    # Мокируем Validation
    validated_emails = []
    mock_validation = Mock()
    
    def mock_validate_batch(emails):
        validated_emails.extend(emails)
        return [ValidationResult("valid", "test", False, False, False) for _ in emails]
    
    mock_validation.validate_batch = mock_validate_batch
    
    from sender import importer
    monkeypatch.setattr(importer, "Validation", lambda cfg: mock_validation)
    
    stats = validate_recipients(store, config, only_unknown=True)
    
    # Должен провалидировать только unknown
    assert stats["total"] == 1
    assert "unknown@test.com" in validated_emails
    assert "already@valid.com" not in validated_emails


def test_validate_recipients_limit(store, config, monkeypatch):
    """Проверяет что limit ограничивает валидацию."""
    # Добавляем несколько получателей
    for i in range(10):
        store.bulk_upsert_recipients([
            RecipientIn(email=f"user{i}@example.com", domain="example.com")
        ])
    
    mock_validation = Mock()
    mock_validation.validate_batch = lambda emails: [
        ValidationResult("valid", "test", False, False, False) for _ in emails
    ]
    
    from sender import importer
    monkeypatch.setattr(importer, "Validation", lambda cfg: mock_validation)
    
    stats = validate_recipients(store, config, limit=5)
    
    assert stats["total"] == 5


def test_validate_recipients_progress_callback(store, config, monkeypatch):
    """Проверяет что progress_cb вызывается при валидации."""
    # Добавляем получателей
    for i in range(1500):
        store.bulk_upsert_recipients([
            RecipientIn(email=f"user{i}@example.com", domain="example.com")
        ])
    
    mock_validation = Mock()
    mock_validation.validate_batch = lambda emails: [
        ValidationResult("valid", "test", False, False, False) for _ in emails
    ]
    
    from sender import importer
    monkeypatch.setattr(importer, "Validation", lambda cfg: mock_validation)
    
    calls = []
    
    def progress_cb(count):
        calls.append(count)
    
    validate_recipients(store, config, progress_cb=progress_cb, batch_size=200)
    
    # Должно быть вызвано на 1000 и финальном
    assert 1000 in calls
    assert calls[-1] == 1500


def test_validate_recipients_empty(store, config, monkeypatch):
    """Проверяет поведение когда нечего валидировать."""
    mock_validation = Mock()
    
    from sender import importer
    monkeypatch.setattr(importer, "Validation", lambda cfg: mock_validation)
    
    stats = validate_recipients(store, config)
    
    assert stats["total"] == 0
    assert stats["valid"] == 0


def test_import_csv_comma_delimiter(store, tmp_path):
    """Проверяет импорт CSV с запятой как разделителем."""
    csv_path = tmp_path / "comma.csv"
    csv_path.write_text(
        "email,company,segment\n"
        "user@example.com,Test Inc,B2B\n"
        "admin@test.ru,Another Co,B2C\n",
        encoding="utf-8"
    )
    
    stats = import_csv(store, str(csv_path))
    
    assert stats["total_rows"] == 2
    assert stats["imported"] == 2


def test_import_csv_with_extras(store, tmp_path):
    """Проверяет импорт с дополнительными полями."""
    csv_path = tmp_path / "extras.csv"
    csv_path.write_text(
        "Email;ИНН;Название;ОКВЭД;Сегмент;Контакт;Источник\n"
        "ceo@corp.ru;1234567890;Корпорация;62.01;Enterprise;Иванов И.И.;партнёры\n",
        encoding="utf-8"
    )
    
    stats = import_csv(store, str(csv_path))
    assert stats["imported"] == 1
    
    recipients = list(store.iter_recipients())
    r = recipients[0]
    assert r.email == "ceo@corp.ru"
    assert r.inn == "1234567890"
    assert r.company_name == "Корпорация"
    assert r.okved == "62.01"
    assert r.segment == "Enterprise"
    assert r.contact_name == "Иванов И.И."
    assert r.source == "партнёры"


def test_import_csv_email_normalization(store, tmp_path):
    """Проверяет что email нормализуются перед записью."""
    csv_path = tmp_path / "normalize.csv"
    csv_path.write_text(
        "Email\n"
        "  Admin@Example.COM  \n"
        "User@TEST.ru\n",
        encoding="utf-8"
    )
    
    import_csv(store, str(csv_path))
    
    recipients = list(store.iter_recipients())
    emails = {r.email for r in recipients}
    assert "admin@example.com" in emails
    assert "user@test.ru" in emails


def test_import_suppression_cp1251(store, tmp_path):
    """Проверяет импорт файла подавления в cp1251."""
    supp_path = tmp_path / "cp1251.txt"
    supp_path.write_text(
        "конкурент.рф\n"
        "соперник.ru\n",
        encoding="cp1251"
    )
    
    added = import_suppression(store, str(supp_path), scope="domain")
    assert added == 2


def test_validate_recipients_batch_processing(store, config, monkeypatch):
    """Проверяет батчевую обработку при валидации."""
    # Добавляем 5 получателей
    for i in range(5):
        store.bulk_upsert_recipients([
            RecipientIn(email=f"user{i}@example.com", domain="example.com")
        ])
    
    batch_sizes = []
    mock_validation = Mock()
    
    def mock_validate_batch(emails):
        batch_sizes.append(len(emails))
        return [ValidationResult("valid", "test", False, False, False) for _ in emails]
    
    mock_validation.validate_batch = mock_validate_batch
    
    from sender import importer
    monkeypatch.setattr(importer, "Validation", lambda cfg: mock_validation)
    
    validate_recipients(store, config, batch_size=2)
    
    # Должно быть 3 батча: 2, 2, 1
    assert batch_sizes == [2, 2, 1]
