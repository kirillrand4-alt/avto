"""Unit tests for sender.unsub_server.

Сервер запускается в отдельном потоке с реальным Store (SQLite в tmp_path),
реальным Suppression и Config из BASE_YAML. Запросы выполняются через
urllib.request к localhost. Токены генерируются через Unsub.make_token().
"""

import os
import socket
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.config import Config  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.unsub import Unsub  # noqa: E402
from sender.unsub_server import make_server  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402


def _find_free_port() -> int:
    """Найти свободный TCP-порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def _now() -> str:
    """Текущее время в ISO формате UTC."""
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def db_path(tmp_path):
    """Путь к временной базе данных."""
    return str(tmp_path / "test.db")


@pytest.fixture
def config(tmp_path):
    """Конфигурация с переменными окружения для паролей."""
    os.environ["BOX1_PASSWORD"] = "test_pass1"
    os.environ["BOX2_PASSWORD"] = "test_pass2"
    os.environ["BOX3_PASSWORD"] = "test_pass3"
    os.environ["BOX4_PASSWORD"] = "test_pass4"
    os.environ["BOX5_PASSWORD"] = "test_pass5"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    
    config_path = tmp_path / "config.yaml"
    yaml_content = BASE_YAML.replace("db.db", str(tmp_path / "test.db"))
    config_path.write_text(yaml_content, encoding="utf-8")
    
    return Config.load(str(config_path))


@pytest.fixture
def store(db_path):
    """Хранилище с инициализированной схемой."""
    s = Store(db_path)
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def suppression(store):
    """Менеджер подавления рассылок."""
    return Suppression(store)


@pytest.fixture
def unsub(config, store, suppression):
    """Экземпляр Unsub для генерации токенов."""
    return Unsub(config, store, suppression)


@pytest.fixture
def recipient_id(store):
    """Создать тестового получателя через публичный API store."""
    from sender.store import RecipientIn
    return store.upsert_recipient(
        RecipientIn(email="test@example.com", domain="example.com"))


@pytest.fixture
def server_url(config, store, suppression):
    """Запустить сервер в отдельном потоке и вернуть базовый URL."""
    port = _find_free_port()
    server = make_server(config, store, suppression, host="127.0.0.1", port=port)
    
    def run_server():
        server.serve_forever()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    
    # Подождать готовности сервера
    max_attempts = 50
    for _ in range(max_attempts):
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.1)
            break
        except Exception:
            time.sleep(0.01)
    
    yield f"http://127.0.0.1:{port}"
    
    server.shutdown()
    server.server_close()
    thread.join(timeout=1)


def test_post_valid_token_creates_suppression(server_url, unsub, recipient_id, store):
    """POST с валидным токеном создаёт запись в suppression."""
    token = unsub.make_token(recipient_id, 1)
    
    req = Request(
        f"{server_url}/u?t={token}",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    
    response = urlopen(req)
    assert response.status == 200
    body = response.read().decode("utf-8")
    assert body == "OK"
    
    # Проверяем suppression в БД
    result = store.suppression_lookup(email="test@example.com", domain="example.com", inn=None)
    assert result is not None
    assert result.scope == "email"
    assert result.value == "test@example.com"
    assert result.reason == "unsubscribe"


def test_post_valid_token_idempotent(server_url, unsub, recipient_id, store):
    """Повторный POST с тем же токеном идемпотентен."""
    token = unsub.make_token(recipient_id, 1)
    
    # Первый запрос
    req1 = Request(
        f"{server_url}/u?t={token}",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    response1 = urlopen(req1)
    assert response1.status == 200
    
    # Второй запрос
    req2 = Request(
        f"{server_url}/u?t={token}",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    response2 = urlopen(req2)
    assert response2.status == 200
    
    # Проверяем, что запись одна
    conn = store._conn
    cursor = conn.execute(
        "SELECT COUNT(*) FROM suppression WHERE scope='email' AND value=?",
        ("test@example.com",)
    )
    count = cursor.fetchone()[0]
    assert count == 1


def test_post_invalid_token_returns_400(server_url):
    """POST с битым токеном возвращает 400."""
    req = Request(
        f"{server_url}/u?t=invalid_token_xyz",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    
    try:
        urlopen(req)
        pytest.fail("Expected HTTPError 400")
    except HTTPError as e:
        assert e.code == 400
        body = e.read().decode("utf-8")
        assert "Invalid token" in body


def test_post_missing_token_returns_400(server_url):
    """POST без токена возвращает 400."""
    req = Request(
        f"{server_url}/u",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    
    try:
        urlopen(req)
        pytest.fail("Expected HTTPError 400")
    except HTTPError as e:
        assert e.code == 400
        body = e.read().decode("utf-8")
        assert "Missing token parameter" in body


def test_get_with_token_returns_html_form(server_url, unsub, recipient_id, config):
    """GET с токеном возвращает HTML с формой отписки."""
    token = unsub.make_token(recipient_id, 1)
    
    response = urlopen(f"{server_url}/u?t={token}")
    assert response.status == 200
    
    body = response.read().decode("utf-8")
    assert "<!DOCTYPE html>" in body
    assert "<form method=\"POST\"" in body
    assert f"action=\"?t={token}\"" in body
    assert "<button type=\"submit\">Отписаться</button>" in body
    
    # Проверяем атрибуцию
    legal_entity = config.legal().entity
    assert legal_entity in body


def test_get_health_returns_ok(server_url):
    """GET /health возвращает 200 ok."""
    response = urlopen(f"{server_url}/health")
    assert response.status == 200
    body = response.read().decode("utf-8")
    assert body == "ok"


def test_get_unknown_path_returns_404(server_url):
    """GET на неизвестный путь возвращает 404."""
    try:
        urlopen(f"{server_url}/unknown")
        pytest.fail("Expected HTTPError 404")
    except HTTPError as e:
        assert e.code == 404
        body = e.read().decode("utf-8")
        assert "Not Found" in body


def test_post_with_html_accept_returns_html(server_url, unsub, recipient_id, config):
    """POST с Accept: text/html возвращает HTML-страницу."""
    token = unsub.make_token(recipient_id, 1)
    
    req = Request(
        f"{server_url}/u?t={token}",
        data=b"List-Unsubscribe=One-Click",
        method="POST",
        headers={"Accept": "text/html"}
    )
    
    response = urlopen(req)
    assert response.status == 200
    
    body = response.read().decode("utf-8")
    assert "<!DOCTYPE html>" in body
    assert "<h1>Вы отписаны</h1>" in body
    assert "Вы больше не будете получать рассылки" in body
    
    legal_entity = config.legal().entity
    assert legal_entity in body


def test_post_creates_consent_log_entry(server_url, unsub, recipient_id, store):
    """POST создаёт запись в consent_history."""
    token = unsub.make_token(recipient_id, 1)
    
    req = Request(
        f"{server_url}/u?t={token}",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    
    urlopen(req)
    
    # Проверяем consent_history
    history = store.consent_history("test@example.com")
    assert len(history) > 0
    
    found = False
    for entry in history:
        if entry["action"] == "unsubscribe":
            found = True
            assert entry["recipient_id"] == recipient_id
            break
    
    assert found, "unsubscribe action not found in consent_history"


def test_post_unknown_path_returns_404(server_url):
    """POST на неизвестный путь возвращает 404."""
    req = Request(
        f"{server_url}/unknown",
        data=b"test",
        method="POST"
    )
    
    try:
        urlopen(req)
        pytest.fail("Expected HTTPError 404")
    except HTTPError as e:
        assert e.code == 404


def test_get_missing_token_returns_400(server_url):
    """GET /u без токена возвращает 400."""
    try:
        urlopen(f"{server_url}/u")
        pytest.fail("Expected HTTPError 400")
    except HTTPError as e:
        assert e.code == 400
        body = e.read().decode("utf-8")
        assert "Missing token parameter" in body


def test_post_with_body_consumed(server_url, unsub, recipient_id):
    """POST с телом обрабатывается корректно (тело читается)."""
    token = unsub.make_token(recipient_id, 1)
    
    req = Request(
        f"{server_url}/u?t={token}",
        data=b"List-Unsubscribe=One-Click&extra=data",
        method="POST"
    )
    
    response = urlopen(req)
    assert response.status == 200


def test_concurrent_requests(server_url, unsub, store):
    """Несколько одновременных запросов обрабатываются корректно."""
    from sender.store import RecipientIn
    recipients = []
    for i in range(5):
        recipients.append(store.upsert_recipient(
            RecipientIn(email=f"test{i}@example.com", domain="example.com")))
    
    def unsubscribe(rid, email):
        token = unsub.make_token(rid, 1)
        req = Request(
            f"{server_url}/u?t={token}",
            data=b"List-Unsubscribe=One-Click",
            method="POST"
        )
        response = urlopen(req)
        return response.status
    
    threads = []
    for i, rid in enumerate(recipients):
        t = threading.Thread(
            target=lambda r=rid, e=f"test{i}@example.com": unsubscribe(r, e)
        )
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # Проверяем, что все отписались
    for i in range(5):
        result = store.suppression_lookup(email=f"test{i}@example.com", domain="example.com", inn=None)
        assert result is not None


def test_post_empty_body(server_url, unsub, recipient_id):
    """POST с пустым телом обрабатывается корректно."""
    token = unsub.make_token(recipient_id, 1)
    
    req = Request(
        f"{server_url}/u?t={token}",
        data=b"",
        method="POST"
    )
    
    response = urlopen(req)
    assert response.status == 200


def test_server_handles_keyboard_interrupt(config, store, suppression, tmp_path):
    """Сервер корректно обрабатывает KeyboardInterrupt."""
    from sender.unsub_server import run_unsub_server
    
    port = _find_free_port()
    stop_event = threading.Event()
    
    def run():
        run_unsub_server(
            config, store, suppression,
            host="127.0.0.1",
            port=port,
            stop_event=stop_event
        )
    
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    
    # Подождать готовности
    time.sleep(0.1)
    
    # Проверить, что сервер работает
    try:
        urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
    except Exception:
        pass
    
    # Остановить через событие
    stop_event.set()
    thread.join(timeout=2)
    
    assert not thread.is_alive()


def test_multiple_tokens_for_same_recipient(server_url, unsub, recipient_id, store):
    """Несколько токенов для одного получателя работают корректно."""
    token1 = unsub.make_token(recipient_id, 1)
    token2 = unsub.make_token(recipient_id, 1)
    
    # Используем первый токен
    req1 = Request(
        f"{server_url}/u?t={token1}",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    response1 = urlopen(req1)
    assert response1.status == 200
    
    # Используем второй токен
    req2 = Request(
        f"{server_url}/u?t={token2}",
        data=b"List-Unsubscribe=One-Click",
        method="POST"
    )
    response2 = urlopen(req2)
    assert response2.status == 200
    
    # Проверяем, что suppression одна
    conn = store._conn
    cursor = conn.execute(
        "SELECT COUNT(*) FROM suppression WHERE scope='email' AND value=?",
        ("test@example.com",)
    )
    count = cursor.fetchone()[0]
    assert count == 1
