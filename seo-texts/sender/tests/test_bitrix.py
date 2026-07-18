"""Unit tests for sender.bitrix.

HTTP calls are routed to a local http.server on 127.0.0.1 with an ephemeral port.
The handler logs received requests to a shared list for verification. Store is a
minimal fake that tracks append_event calls. Config is a lightweight fake.
"""

import json
import os
import socket
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from typing import Any, Optional
from urllib.parse import urlparse

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.bitrix import (  # noqa: E402
    BitrixClient,
    BitrixError,
    BitrixSink,
    extract_phone,
)


def _get_free_port() -> int:
    """Получает свободный порт для тестового HTTP-сервера."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return s.getsockname()[1]


class RequestLog:
    """Журнал HTTP-запросов для проверки в тестах."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def add(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes
    ) -> None:
        """Сохраняет данные запроса."""
        self.requests.append({
            "method": method,
            "path": path,
            "headers": headers,
            "body": body,
        })

    def clear(self) -> None:
        """Очищает журнал."""
        self.requests.clear()

    def count(self) -> int:
        """Возвращает количество запросов."""
        return len(self.requests)


class MockBitrixHandler(BaseHTTPRequestHandler):
    """HTTP-хендлер для имитации Bitrix24 REST API."""

    log: RequestLog
    response_queue: list[tuple[int, dict]]

    def log_message(self, format: str, *args: Any) -> None:
        """Подавляет стандартное логирование HTTP-сервера."""
        pass

    def do_POST(self) -> None:
        """Обрабатывает POST-запрос к API."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Сохраняем запрос в журнал
        self.log.add(
            method="POST",
            path=self.path,
            headers=dict(self.headers),
            body=body,
        )

        # Берём заготовленный ответ из очереди
        if self.response_queue:
            status_code, response_data = self.response_queue.pop(0)
        else:
            # Дефолтный успешный ответ
            status_code = 200
            response_data = {"result": 42}

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        response_body = json.dumps(response_data).encode("utf-8")
        self.wfile.write(response_body)


class FakeConfig:
    """Лёгковесный конфиг для тестов."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        """Возвращает значение конфига по ключу."""
        return self._data.get(key, default)


class FakeStore:
    """Минимальный стор для отслеживания вызовов append_event."""

    def __init__(self) -> None:
        self.events: list[Any] = []
        self.next_return = (1, True)

    def append_event(self, event: Any) -> tuple[int, bool]:
        """Сохраняет событие и возвращает (event_id, created)."""
        self.events.append(event)
        return self.next_return

    def set_next_return(self, event_id: int, created: bool) -> None:
        """Устанавливает результат следующего append_event."""
        self.next_return = (event_id, created)


class FakeRecipient:
    """Фейковый получатель для тестов."""

    def __init__(
        self,
        recipient_id: int,
        email: str,
        company_name: Optional[str] = None,
        contact_name: Optional[str] = None,
    ) -> None:
        self.id = recipient_id
        self.email = email
        self.company_name = company_name
        self.contact_name = contact_name


@pytest.fixture
def mock_server() -> tuple[str, RequestLog, list]:
    """
    Запускает локальный HTTP-сервер для имитации Bitrix24 API.
    
    Returns:
        Кортеж (base_url, request_log, response_queue)
    """
    port = _get_free_port()
    base_url = f"http://127.0.0.1:{port}/rest/1/tok"

    request_log = RequestLog()
    response_queue: list[tuple[int, dict]] = []

    # Создаём класс хендлера с доступом к shared state
    handler_class = type(
        "TestHandler",
        (MockBitrixHandler,),
        {"log": request_log, "response_queue": response_queue},
    )

    server = HTTPServer(("127.0.0.1", port), handler_class)

    # Запускаем сервер в отдельном потоке
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    yield base_url, request_log, response_queue

    server.shutdown()


def test_bitrix_client_call_success(mock_server: tuple) -> None:
    """BitrixClient.call: успешный POST возвращает результат из поля 'result'."""
    base_url, log, queue = mock_server
    queue.append((200, {"result": 42}))

    client = BitrixClient(base_url, timeout=5.0, retries=1)
    result = client.call("crm.lead.add", {"fields": {"TITLE": "Test"}})

    assert result == 42
    assert log.count() == 1

    req = log.requests[0]
    assert req["method"] == "POST"
    assert req["path"] == "/rest/1/tok/crm.lead.add.json"
    assert req["headers"]["Content-Type"] == "application/json"

    body_data = json.loads(req["body"])
    assert body_data == {"fields": {"TITLE": "Test"}}


def test_bitrix_client_call_api_error(mock_server: tuple) -> None:
    """BitrixClient.call: ответ с 'error' вызывает BitrixError без ретраев."""
    base_url, log, queue = mock_server
    queue.append((200, {"error": "INVALID_TOKEN", "error_description": "Token expired"}))

    client = BitrixClient(base_url, timeout=5.0, retries=3)

    with pytest.raises(BitrixError, match="Token expired"):
        client.call("crm.lead.add", {})

    # Должен быть ровно 1 запрос (без ретраев)
    assert log.count() == 1


def test_bitrix_client_call_server_error_retries(mock_server: tuple) -> None:
    """BitrixClient.call: 500-ошибка вызывает несколько ретраев перед исключением."""
    base_url, log, queue = mock_server

    # Все попытки возвращают 500
    for _ in range(3):
        queue.append((500, {"error": "Internal Server Error"}))

    client = BitrixClient(base_url, timeout=5.0, retries=3)

    with pytest.raises(BitrixError, match="Failed to call .* after 3 attempts"):
        client.call("crm.lead.list", {})

    # Должно быть ровно 3 запроса (начальный + 2 ретрая)
    assert log.count() == 3


def test_bitrix_client_call_client_error_no_retry(mock_server: tuple) -> None:
    """BitrixClient.call: 4xx-ошибка вызывает исключение без ретраев."""
    base_url, log, queue = mock_server
    queue.append((404, {}))

    client = BitrixClient(base_url, timeout=5.0, retries=3)

    with pytest.raises(BitrixError, match="HTTP 404"):
        client.call("crm.lead.get", {"id": 999})

    assert log.count() == 1


def test_bitrix_sink_disabled_without_env(mock_server: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    """BitrixSink: если переменная окружения не установлена, sink disabled."""
    base_url, log, _ = mock_server

    # Удаляем переменную окружения
    monkeypatch.delenv("BITRIX_WEBHOOK_URL", raising=False)

    config = FakeConfig({"bitrix.webhook_env": "BITRIX_WEBHOOK_URL"})
    sink = BitrixSink(config)

    assert not sink.enabled
    assert sink.client is None

    recipient = FakeRecipient(1, "test@example.com")
    result = sink.push_warm_lead(recipient, "thread-123", "Reply text")

    assert result is None
    assert log.count() == 0


def test_bitrix_sink_push_warm_lead_success(mock_server: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    """BitrixSink.push_warm_lead: создаёт лид с корректными полями и возвращает lead_id."""
    base_url, log, queue = mock_server
    queue.append((200, {"result": 100500}))

    monkeypatch.setenv("BITRIX_WEBHOOK_URL", base_url)

    config = FakeConfig({
        "bitrix.webhook_env": "BITRIX_WEBHOOK_URL",
        "bitrix.source_id": "EMAIL",
    })
    store = FakeStore()
    sink = BitrixSink(config, store)

    assert sink.enabled

    recipient = FakeRecipient(
        recipient_id=42,
        email="ceo@acme.com",
        company_name="ACME Corp",
        contact_name="John Doe",
    )
    snippet = "Interested in your proposal!"
    lead_id = sink.push_warm_lead(recipient, "thread-xyz", snippet)

    assert lead_id == 100500
    assert log.count() == 1

    req = log.requests[0]
    assert req["path"] == "/rest/1/tok/crm.lead.add.json"

    body_data = json.loads(req["body"])
    fields = body_data["fields"]

    assert fields["TITLE"] == "Ответ на рассылку: ACME Corp"
    assert fields["EMAIL"] == [{"VALUE": "ceo@acme.com", "VALUE_TYPE": "WORK"}]
    assert fields["SOURCE_ID"] == "EMAIL"
    assert fields["NAME"] == "John Doe"
    assert fields["COMPANY_TITLE"] == "ACME Corp"
    assert "thread-xyz" in fields["COMMENTS"]
    assert snippet in fields["COMMENTS"]

    # Проверяем, что дедуп-событие записано
    assert len(store.events) == 1
    event = store.events[0]
    assert event.dedup_key == "bitrix_lead:thread-xyz"
    assert event.event_type == "bitrix_lead_created"
    assert event.recipient_id == 42


def test_bitrix_sink_dedup_prevents_duplicate(mock_server: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    """BitrixSink.push_warm_lead: дедупликация предотвращает повторное создание лида."""
    base_url, log, queue = mock_server

    monkeypatch.setenv("BITRIX_WEBHOOK_URL", base_url)

    config = FakeConfig({"bitrix.webhook_env": "BITRIX_WEBHOOK_URL"})
    store = FakeStore()

    # Первый вызов: лид создаётся
    store.set_next_return(1, True)
    queue.append((200, {"result": 200}))

    sink = BitrixSink(config, store)
    recipient = FakeRecipient(1, "dup@test.com")

    lead_id = sink.push_warm_lead(recipient, "thread-dup", "First")
    assert lead_id == 200
    assert log.count() == 1

    # Второй вызов: дедуп срабатывает (append_event возвращает created=False)
    store.set_next_return(1, False)
    lead_id = sink.push_warm_lead(recipient, "thread-dup", "Second")

    assert lead_id is None
    # HTTP-запрос не должен быть выполнен
    assert log.count() == 1


def test_bitrix_sink_phone_extraction(mock_server: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    """BitrixSink.push_warm_lead: телефон из snippet попадает в поле PHONE."""
    base_url, log, queue = mock_server
    queue.append((200, {"result": 300}))

    monkeypatch.setenv("BITRIX_WEBHOOK_URL", base_url)

    config = FakeConfig({"bitrix.webhook_env": "BITRIX_WEBHOOK_URL"})
    sink = BitrixSink(config)

    recipient = FakeRecipient(1, "phone@test.com")
    snippet = "Call me at +7 (495) 123-45-67 please"

    sink.push_warm_lead(recipient, "thread-phone", snippet)

    req = log.requests[0]
    body_data = json.loads(req["body"])
    fields = body_data["fields"]

    assert "PHONE" in fields
    assert fields["PHONE"] == [{"VALUE": "+74951234567", "VALUE_TYPE": "WORK"}]


def test_bitrix_sink_default_responsible(mock_server: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    """BitrixSink.push_warm_lead: default_responsible из конфига попадает в ASSIGNED_BY_ID."""
    base_url, log, queue = mock_server
    queue.append((200, {"result": 400}))

    monkeypatch.setenv("BITRIX_WEBHOOK_URL", base_url)

    config = FakeConfig({
        "bitrix.webhook_env": "BITRIX_WEBHOOK_URL",
        "bitrix.default_responsible": 10,
    })
    sink = BitrixSink(config)

    recipient = FakeRecipient(1, "assigned@test.com")
    sink.push_warm_lead(recipient, "thread-assigned", "Text")

    req = log.requests[0]
    body_data = json.loads(req["body"])
    fields = body_data["fields"]

    assert fields["ASSIGNED_BY_ID"] == 10


def test_bitrix_sink_no_default_responsible(mock_server: tuple, monkeypatch: pytest.MonkeyPatch) -> None:
    """BitrixSink.push_warm_lead: без default_responsible ключ ASSIGNED_BY_ID отсутствует."""
    base_url, log, queue = mock_server
    queue.append((200, {"result": 500}))

    monkeypatch.setenv("BITRIX_WEBHOOK_URL", base_url)

    config = FakeConfig({"bitrix.webhook_env": "BITRIX_WEBHOOK_URL"})
    sink = BitrixSink(config)

    recipient = FakeRecipient(1, "noassigned@test.com")
    sink.push_warm_lead(recipient, "thread-noassigned", "Text")

    req = log.requests[0]
    body_data = json.loads(req["body"])
    fields = body_data["fields"]

    assert "ASSIGNED_BY_ID" not in fields
