"""Unit tests for sender.postoffice.

Тесты используют реальный локальный HTTP-сервер (threading) на 127.0.0.1 со свободным
портом для проверки интеграции с API Постофиса Mail.ru. Все сетевые вызовы остаются
локальными, без обращения к внешним хостам.
"""

import json
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.postoffice import (  # noqa: E402
    PostofficeClient,
    PostofficeError,
    reputation_alert,
)


class FakeConfig:
    """Легковесный fake-конфиг для тестов."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение конфигурации."""
        return self._data.get(key, default)


class RequestCapture:
    """Хранилище захваченных HTTP-запросов."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.lock = threading.Lock()

    def add(self, request_data: dict) -> None:
        """Добавить захваченный запрос."""
        with self.lock:
            self.requests.append(request_data)

    def clear(self) -> None:
        """Очистить список запросов."""
        with self.lock:
            self.requests.clear()

    def get_all(self) -> list[dict]:
        """Получить все захваченные запросы."""
        with self.lock:
            return list(self.requests)


class MockPostofficeHandler(BaseHTTPRequestHandler):
    """HTTP-обработчик для мок-сервера Постофиса."""

    capture: RequestCapture
    responses: dict[str, Any]

    def log_message(self, format: str, *args: Any) -> None:
        """Отключить логи встроенного сервера."""
        pass

    def do_GET(self) -> None:
        """Обработать GET-запрос."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # Захватываем запрос
        request_data = {
            "method": "GET",
            "path": path,
            "params": {k: v[0] if len(v) == 1 else v for k, v in params.items()},
            "headers": dict(self.headers),
        }
        self.capture.add(request_data)

        # Ищем подходящий response
        response_key = path
        if response_key in self.responses:
            response_config = self.responses[response_key]

            # Поддержка специальных ответов
            if response_config.get("type") == "error_500":
                self.send_response(500)
                self.end_headers()
                self.wfile.write(b"Internal Server Error")
                return

            if response_config.get("type") == "invalid_json":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"not a valid json{")
                return

            if response_config.get("type") == "error_400":
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Bad Request")
                return

            # Обычный JSON-ответ
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps(response_config.get("body", {}))
            self.wfile.write(body.encode("utf-8"))
            return

        # Если путь не найден
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")


def _find_free_port() -> int:
    """Найти свободный порт для локального сервера."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def mock_server():
    """Фикстура для локального мок-сервера Постофиса."""
    port = _find_free_port()
    capture = RequestCapture()
    responses = {}

    # Создаём класс обработчика с доступом к capture и responses
    class Handler(MockPostofficeHandler):
        pass

    Handler.capture = capture
    Handler.responses = responses

    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield {
        "port": port,
        "base_url": f"http://127.0.0.1:{port}",
        "capture": capture,
        "responses": responses,
    }

    server.shutdown()


def test_client_disabled_without_token():
    """Клиент в режиме disabled без токена: все методы возвращают None."""
    # Убираем токен из окружения
    old_token = os.environ.pop("POSTOFFICE_TOKEN", None)
    try:
        config = FakeConfig({})
        client = PostofficeClient(config)

        assert client._disabled is True

        result = client.domain_summary("example.com")
        assert result is None

        result = client.spam_rate("example.com", "2024-01-01", "2024-01-07")
        assert result is None

        result = client.report(["example.com"])
        assert result == {"domains": []}

    finally:
        if old_token is not None:
            os.environ["POSTOFFICE_TOKEN"] = old_token


def test_domain_summary_success(mock_server):
    """domain_summary: успешный запрос с проверкой path, params и токена."""
    # Настраиваем мок-ответ
    mock_server["responses"]["/domain/summary"] = {
        "body": {
            "domain": "example.com",
            "reputation": "good",
            "status": "active"
        }
    }

    # Устанавливаем токен
    os.environ["POSTOFFICE_TOKEN"] = "test_token_123"
    try:
        config = FakeConfig({
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.summary_path": "/domain/summary",
            "postoffice.timeout": 5,
            "postoffice.retries": 0,
        })

        client = PostofficeClient(config)
        result = client.domain_summary("example.com")

        # Проверяем результат
        assert result is not None
        assert result["domain"] == "example.com"
        assert result["reputation"] == "good"

        # Проверяем захваченные запросы
        requests = mock_server["capture"].get_all()
        assert len(requests) == 1

        req = requests[0]
        assert req["method"] == "GET"
        assert req["path"] == "/domain/summary"
        assert req["params"]["domain"] == "example.com"
        assert req["params"]["access_token"] == "test_token_123"
        
        # Проверяем оба способа передачи токена
        assert "Authorization" in req["headers"]
        assert req["headers"]["Authorization"] == "Bearer test_token_123"

    finally:
        os.environ.pop("POSTOFFICE_TOKEN", None)


def test_spam_rate_with_dates(mock_server):
    """spam_rate: проверка передачи дат в параметрах запроса."""
    mock_server["responses"]["/domain/spam"] = {
        "body": {
            "domain": "example.com",
            "spam_rate": 0.5,
            "period": "2024-01-01 to 2024-01-07"
        }
    }

    os.environ["POSTOFFICE_TOKEN"] = "test_token_456"
    try:
        config = FakeConfig({
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.spam_path": "/domain/spam",
            "postoffice.timeout": 5,
            "postoffice.retries": 0,
        })

        client = PostofficeClient(config)
        result = client.spam_rate("example.com", "2024-01-01", "2024-01-07")

        assert result is not None
        assert result["spam_rate"] == 0.5

        requests = mock_server["capture"].get_all()
        assert len(requests) == 1

        req = requests[0]
        assert req["path"] == "/domain/spam"
        assert req["params"]["domain"] == "example.com"
        assert req["params"]["date_from"] == "2024-01-01"
        assert req["params"]["date_to"] == "2024-01-07"

    finally:
        os.environ.pop("POSTOFFICE_TOKEN", None)


def test_retry_on_500_error(mock_server):
    """HTTP 500: клиент делает ретрай и затем выбрасывает PostofficeError."""
    mock_server["responses"]["/domain/summary"] = {
        "type": "error_500"
    }

    os.environ["POSTOFFICE_TOKEN"] = "test_token_789"
    try:
        config = FakeConfig({
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.summary_path": "/domain/summary",
            "postoffice.timeout": 5,
            "postoffice.retries": 2,
            "postoffice.retry_delay": 0.05,
        })

        client = PostofficeClient(config)

        with pytest.raises(PostofficeError) as exc_info:
            client.domain_summary("example.com")

        assert "500" in str(exc_info.value)

        # Проверяем количество попыток: начальная + 2 ретрая = 3
        requests = mock_server["capture"].get_all()
        assert len(requests) == 3

    finally:
        os.environ.pop("POSTOFFICE_TOKEN", None)


def test_invalid_json_response(mock_server):
    """Некорректный JSON в ответе: выбрасывается PostofficeError."""
    mock_server["responses"]["/domain/summary"] = {
        "type": "invalid_json"
    }

    os.environ["POSTOFFICE_TOKEN"] = "test_token_json"
    try:
        config = FakeConfig({
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.summary_path": "/domain/summary",
            "postoffice.timeout": 5,
            "postoffice.retries": 0,
        })

        client = PostofficeClient(config)

        with pytest.raises(PostofficeError) as exc_info:
            client.domain_summary("example.com")

        assert "JSON" in str(exc_info.value)

    finally:
        os.environ.pop("POSTOFFICE_TOKEN", None)


def test_report_with_partial_failure(mock_server):
    """report: один домен с ошибкой, второй успешен — оба в результате."""
    # Настраиваем ответы: для domain1.com - успех, для domain2.com - ошибка
    mock_server["responses"]["/domain/summary"] = {
        "type": "error_400"
    }
    mock_server["responses"]["/domain/spam"] = {
        "body": {
            "spam_rate": 0.3
        }
    }

    call_count = {"summary": 0}

    # Создаём динамический обработчик для разных доменов
    original_do_get = MockPostofficeHandler.do_GET

    def custom_do_get(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        domain = params.get("domain", [None])[0]

        # Захватываем запрос
        request_data = {
            "method": "GET",
            "path": path,
            "params": {k: v[0] if len(v) == 1 else v for k, v in params.items()},
            "headers": dict(self.headers),
        }
        self.capture.add(request_data)

        if path == "/domain/summary":
            call_count["summary"] += 1
            if domain == "domain1.com":
                # Первый домен - успех
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = json.dumps({"domain": "domain1.com", "reputation": "good"})
                self.wfile.write(body.encode("utf-8"))
                return
            elif domain == "domain2.com":
                # Второй домен - ошибка
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Bad Request for domain2.com")
                return

        if path == "/domain/spam" and domain == "domain1.com":
            # Спам-статистика для первого домена
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps({"spam_rate": 0.3})
            self.wfile.write(body.encode("utf-8"))
            return

        # Fallback
        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    MockPostofficeHandler.do_GET = custom_do_get

    os.environ["POSTOFFICE_TOKEN"] = "test_token_report"
    try:
        config = FakeConfig({
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.summary_path": "/domain/summary",
            "postoffice.spam_path": "/domain/spam",
            "postoffice.timeout": 5,
            "postoffice.retries": 0,
        })

        client = PostofficeClient(config)
        result = client.report(["domain1.com", "domain2.com"])

        # Проверяем результат
        assert "domains" in result
        domains = result["domains"]
        assert len(domains) == 2

        # Первый домен успешен
        domain1 = next(d for d in domains if d["domain"] == "domain1.com")
        assert "summary" in domain1
        assert domain1["summary"]["reputation"] == "good"
        assert "spam" in domain1
        assert domain1["spam"]["spam_rate"] == 0.3
        assert "error" not in domain1

        # Второй домен с ошибкой
        domain2 = next(d for d in domains if d["domain"] == "domain2.com")
        assert "error" in domain2
        assert "summary" in domain2["error"]

    finally:
        MockPostofficeHandler.do_GET = original_do_get
        os.environ.pop("POSTOFFICE_TOKEN", None)


def test_reputation_alert_high_spam_rate():
    """reputation_alert: высокий spam_rate генерирует алерт."""
    report = {
        "domains": [
            {
                "domain": "example.com",
                "summary": {"reputation": "good"},
                "spam": {"spam_rate": 2.5}
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)

    assert len(alerts) == 1
    assert "example.com" in alerts[0]
    assert "2.5" in alerts[0] or "2.50" in alerts[0]
    assert "1.0" in alerts[0] or "1.00" in alerts[0]


def test_reputation_alert_below_threshold():
    """reputation_alert: spam_rate ниже порога — алертов нет."""
    report = {
        "domains": [
            {
                "domain": "example.com",
                "summary": {"reputation": "good"},
                "spam": {"spam_rate": 0.5}
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)
    assert len(alerts) == 0


def test_reputation_alert_no_spam_keys():
    """reputation_alert: отсутствуют ключи спама — алертов нет."""
    report = {
        "domains": [
            {
                "domain": "example.com",
                "summary": {"reputation": "good"},
                "spam": {}
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)
    assert len(alerts) == 0


def test_reputation_alert_with_error():
    """reputation_alert: домен с ошибкой генерирует алерт об ошибке."""
    report = {
        "domains": [
            {
                "domain": "error-domain.com",
                "error": "summary: HTTP 500"
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)

    assert len(alerts) == 1
    assert "error-domain.com" in alerts[0]
    assert "Ошибка" in alerts[0]
    assert "HTTP 500" in alerts[0]


def test_reputation_alert_nested_spam_rate():
    """reputation_alert: гибкий поиск spam_rate во вложенных структурах."""
    report = {
        "domains": [
            {
                "domain": "nested.com",
                "summary": {
                    "reputation": "good",
                    "metrics": {
                        "spam_rate": 1.8
                    }
                },
                "spam": {}
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)

    assert len(alerts) == 1
    assert "nested.com" in alerts[0]
    assert "1.8" in alerts[0] or "1.80" in alerts[0]


def test_reputation_alert_multiple_domains():
    """reputation_alert: несколько доменов, только один превышает порог."""
    report = {
        "domains": [
            {
                "domain": "good.com",
                "spam": {"spam_rate": 0.3}
            },
            {
                "domain": "bad.com",
                "spam": {"spam_rate": 2.0}
            },
            {
                "domain": "ok.com",
                "spam": {"spam_rate": 0.9}
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)

    assert len(alerts) == 1
    assert "bad.com" in alerts[0]


def test_reputation_alert_empty_report():
    """reputation_alert: пустой отчёт возвращает пустой список алертов."""
    report = {"domains": []}
    alerts = reputation_alert(report, spam_threshold_pct=1.0)
    assert len(alerts) == 0


def test_client_custom_paths(mock_server):
    """Клиент использует кастомные пути из конфигурации."""
    mock_server["responses"]["/custom/summary"] = {
        "body": {"domain": "custom.com", "status": "ok"}
    }
    mock_server["responses"]["/custom/spam"] = {
        "body": {"spam_rate": 0.1}
    }

    os.environ["POSTOFFICE_TOKEN"] = "test_token_custom"
    try:
        config = FakeConfig({
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.summary_path": "/custom/summary",
            "postoffice.spam_path": "/custom/spam",
            "postoffice.timeout": 5,
            "postoffice.retries": 0,
        })

        client = PostofficeClient(config)
        
        result1 = client.domain_summary("custom.com")
        assert result1["status"] == "ok"

        result2 = client.spam_rate("custom.com", "2024-01-01", "2024-01-07")
        assert result2["spam_rate"] == 0.1

        requests = mock_server["capture"].get_all()
        assert len(requests) == 2
        assert requests[0]["path"] == "/custom/summary"
        assert requests[1]["path"] == "/custom/spam"

    finally:
        os.environ.pop("POSTOFFICE_TOKEN", None)


def test_client_custom_token_env_variable(mock_server):
    """Клиент читает токен из кастомной переменной окружения."""
    mock_server["responses"]["/domain/summary"] = {
        "body": {"domain": "test.com"}
    }

    os.environ["CUSTOM_POSTOFFICE_TOKEN"] = "custom_token_value"
    try:
        config = FakeConfig({
            "postoffice.token_env": "CUSTOM_POSTOFFICE_TOKEN",
            "postoffice.base_url": mock_server["base_url"],
            "postoffice.summary_path": "/domain/summary",
            "postoffice.timeout": 5,
            "postoffice.retries": 0,
        })

        client = PostofficeClient(config)
        assert client._disabled is False

        result = client.domain_summary("test.com")
        assert result is not None

        requests = mock_server["capture"].get_all()
        assert len(requests) == 1
        assert requests[0]["params"]["access_token"] == "custom_token_value"

    finally:
        os.environ.pop("CUSTOM_POSTOFFICE_TOKEN", None)


def test_reputation_alert_alternative_spam_keys():
    """reputation_alert: распознаёт альтернативные ключи (complaints, spam_pct)."""
    report = {
        "domains": [
            {
                "domain": "alt1.com",
                "spam": {"complaints": 1.5}
            },
            {
                "domain": "alt2.com",
                "summary": {"spam_pct": 2.2}
            },
            {
                "domain": "alt3.com",
                "spam": {"complaint_rate": 0.5}
            }
        ]
    }

    alerts = reputation_alert(report, spam_threshold_pct=1.0)

    # Должны быть алерты для alt1.com и alt2.com
    assert len(alerts) == 2
    alert_domains = [a for a in alerts if "alt1.com" in a or "alt2.com" in a]
    assert len(alert_domains) == 2
