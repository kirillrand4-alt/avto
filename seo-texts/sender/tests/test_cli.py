"""Тесты CLI-интерфейса сервиса рассылки."""

import json
import os
from pathlib import Path

import pytest

from sender import cli
from sender.store import Store
from sender.tests.test_config import BASE_YAML


@pytest.fixture
def config_path(tmp_path):
    """Создаёт валидный конфиг в tmp_path."""
    yaml_content = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "db.sqlite"))
    config_file = tmp_path / "sender.yaml"
    config_file.write_text(yaml_content, encoding="utf-8")
    
    # Устанавливаем пароли и секрет в окружение
    os.environ["BOX1_PASSWORD"] = "pass1"
    os.environ["BOX2_PASSWORD"] = "pass2"
    os.environ["BOX3_PASSWORD"] = "pass3"
    os.environ["BOX4_PASSWORD"] = "pass4"
    os.environ["BOX5_PASSWORD"] = "pass5"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_12345"
    
    yield config_file
    
    # Очистка окружения
    for key in ["BOX1_PASSWORD", "BOX2_PASSWORD", "BOX3_PASSWORD", 
                "BOX4_PASSWORD", "BOX5_PASSWORD", "UNSUB_SIGNING_SECRET"]:
        os.environ.pop(key, None)


@pytest.fixture
def db_path(tmp_path):
    """Возвращает путь к БД."""
    return tmp_path / "db.sqlite"


@pytest.fixture
def csv_file(tmp_path):
    """Создаёт тестовый CSV-файл."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(
        "email,inn,company\n"
        "test1@example.com,1234567890,Company A\n"
        "test2@example.com,0987654321,Company B\n",
        encoding="utf-8"
    )
    return csv_path


@pytest.fixture
def body_file(tmp_path):
    """Создаёт файл с телом письма."""
    body_path = tmp_path / "body.txt"
    body_path.write_text("Привет, {{name}}!", encoding="utf-8")
    return body_path


def test_init_db_success(config_path, db_path, capsys):
    """init-db создаёт файл БД и возвращает код 0."""
    exit_code = cli.main(["--config", str(config_path), "init-db"])
    
    assert exit_code == 0
    assert db_path.exists()
    
    captured = capsys.readouterr()
    assert "Database initialized" in captured.out
    assert str(db_path) in captured.out


def test_init_db_invalid_config(tmp_path, capsys):
    """init-db с битым конфигом возвращает код 1 без трейсбека."""
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text("invalid: yaml: content:", encoding="utf-8")
    
    exit_code = cli.main(["--config", str(bad_config), "init-db"])
    
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_init_db_missing_config(capsys):
    """init-db с несуществующим конфигом возвращает код 1."""
    exit_code = cli.main(["--config", "/nonexistent/config.yaml", "init-db"])
    
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_import_csv_success(config_path, csv_file, capsys):
    """import импортирует CSV и выводит счётчики."""
    cli.main(["--config", str(config_path), "init-db"])
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main(["--config", str(config_path), "import", str(csv_file)])
    
    assert exit_code == 0
    
    captured = capsys.readouterr()
    output = json.loads(captured.out[captured.out.index("{"):])
    
    assert output["imported"] == 2
    assert output["skipped_invalid"] == 0
    
    # Проверяем, что записи попали в Store
    db_path = Path(str(config_path).replace("sender.yaml", "db.sqlite"))
    store = Store(str(db_path))
    recipients = store._conn.execute("SELECT COUNT(*) FROM recipients").fetchone()[0]
    assert recipients == 2


def test_import_csv_with_limit(config_path, csv_file, capsys):
    """import с --limit ограничивает количество записей."""
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main([
        "--config", str(config_path),
        "import", str(csv_file),
        "--limit", "1"
    ])
    
    assert exit_code == 0
    
    captured = capsys.readouterr()
    output = json.loads(captured.out[captured.out.index("{"):])
    assert output["imported"] == 1


def test_import_csv_with_map(config_path, tmp_path, capsys):
    """import с --map маппит колонки."""
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text(
        "EmailAddr,TIN,Name\n"
        "user@test.com,1111111111,Test Corp\n",
        encoding="utf-8"
    )
    
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main([
        "--config", str(config_path),
        "import", str(csv_path),
        "--map", "email=EmailAddr,inn=TIN"
    ])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out[captured.out.index("{"):])
    assert output["imported"] == 1


def test_import_csv_missing_file(config_path, capsys):
    """import с несуществующим файлом возвращает код 1."""
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main([
        "--config", str(config_path),
        "import", "/nonexistent/file.csv"
    ])
    
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Error:" in captured.err


def test_suppress_import_success(config_path, tmp_path, capsys):
    """suppress-import импортирует записи подавления."""
    suppress_file = tmp_path / "suppress.txt"
    suppress_file.write_text("competitor.com\nspam-domain.org\n", encoding="utf-8")
    
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main([
        "--config", str(config_path),
        "suppress-import", str(suppress_file),
        "--scope", "domain",
        "--reason", "competitor"
    ])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Imported 2 suppression entries" in captured.out
    assert "scope=domain" in captured.out


def test_suppress_import_inn_scope(config_path, tmp_path, capsys):
    """suppress-import с scope=inn импортирует ИНН."""
    suppress_file = tmp_path / "inns.txt"
    suppress_file.write_text("1234567890\n0987654321\n", encoding="utf-8")
    
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main([
        "--config", str(config_path),
        "suppress-import", str(suppress_file),
        "--scope", "inn"
    ])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "scope=inn" in captured.out


def test_validate_success(config_path, csv_file, capsys):
    """validate валидирует email получателей."""
    cli.main(["--config", str(config_path), "init-db"])
    cli.main(["--config", str(config_path), "import", str(csv_file)])
    
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main(["--config", str(config_path), "validate"])
    
    assert exit_code == 0
    captured = capsys.readouterr()
    output = json.loads(captured.out[captured.out.rindex("{"):])
    assert "total" in output


def test_validate_with_limit(config_path, csv_file, capsys):
    """validate с --limit ограничивает количество."""
    cli.main(["--config", str(config_path), "init-db"])
    cli.main(["--config", str(config_path), "import", str(csv_file)])
    
    exit_code = cli.main([
        "--config", str(config_path),
        "validate",
        "--limit", "1"
    ])
    
    assert exit_code == 0


def test_status_lists_mailboxes(config_path, capsys):
    """status: перечисляет ящики из конфига (регресс: mb_cfg.email не существует)."""
    cli.main(["--config", str(config_path), "init-db"])

    exit_code = cli.main(["--config", str(config_path), "status"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Mailbox Status" in captured.out
    # все ящики конфига должны быть в выводе по mailbox_id
    assert "box1@" in captured.out


def test_pause_resume_global(config_path, capsys):
    """pause/resume --scope global проходят по всем ящикам конфига."""
    cli.main(["--config", str(config_path), "init-db"])

    exit_code = cli.main([
        "--config", str(config_path),
        "pause", "--scope", "global", "--reason", "test"
    ])
    assert exit_code == 0
    assert "paused" in capsys.readouterr().out.lower()

    exit_code = cli.main(["--config", str(config_path), "resume"])
    assert exit_code == 0
    assert "resumed" in capsys.readouterr().out.lower()


def test_user_rotate_2fa(config_path, db_path, capsys):
    """user-rotate-2fa: новый секрет, старый перестаёт действовать, аудит есть."""
    from sender.auth import Auth, totp_now

    cli.main(["--config", str(config_path), "init-db"])
    capsys.readouterr()  # сброс вывода init-db, дальше парсим чистый JSON
    os.environ["SENDER_NEW_USER_PASSWORD"] = "rotatepass1"
    try:
        assert cli.main([
            "--config", str(config_path), "user-create",
            "--username", "kirill", "--role", "owner", "--enable-2fa",
        ]) == 0
    finally:
        os.environ.pop("SENDER_NEW_USER_PASSWORD", None)
    old_secret = json.loads(capsys.readouterr().out)["totp_uri"].split("secret=")[1].split("&")[0]

    exit_code = cli.main([
        "--config", str(config_path), "user-rotate-2fa", "--username", "kirill"])
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    new_secret = out["totp_uri"].split("secret=")[1].split("&")[0]
    assert new_secret != old_secret and out["username"] == "kirill"

    store = Store(str(db_path))
    user = store.get_user_by_username("kirill")
    assert user.totp_secret == new_secret  # старый секрет затёрт
    auth = Auth(store)
    with pytest.raises(Exception):  # старый TOTP-код больше не подходит
        auth.login(username="kirill", password="rotatepass1",
                   totp_code=totp_now(old_secret))
    token = auth.login(username="kirill", password="rotatepass1",
                       totp_code=totp_now(new_secret))
    assert token
    assert any(a["action"] == "user.rotate_2fa" for a in store.list_audit())


def test_user_rotate_2fa_unknown_user(config_path, capsys):
    """user-rotate-2fa по несуществующему логину: код 1, понятная ошибка."""
    cli.main(["--config", str(config_path), "init-db"])
    exit_code = cli.main([
        "--config", str(config_path), "user-rotate-2fa", "--username", "nosuch"])
    assert exit_code == 1
    assert "not found" in capsys.readouterr().err
