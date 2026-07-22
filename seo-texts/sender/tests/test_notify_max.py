"""Unit tests for sender.notify — Max channel.

Тесты канала Max (VK Мессенджер) в notify.py. Использует локальный http.server
на 127.0.0.1 со свободным портом для имитации Max Bot API. Проверяет работу
канала max, режим both, обратную совместимость, обработку ошибок и общий дебаунс.
"""

import json
import os
import socket
import sys
import threading
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse, parse_qs

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.notify import Notifier, notify_gate_trips  # noqa: E402


def _get_free_port() -> int:
    """Получить свободный TCP-порт."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class MaxMockHandler(BaseHTTPRequestHandler):
    """HTTP-хендлер для имитации Max Bot API."""
    
    def log_message(self, format: str, *args: Any) -> None:
        """Подавляем логи сервера."""
        pass
    
    def do_POST(self) -> None:
        """Обработка POST-запросов."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        
        request_data = {
            "path": parsed_url.path,
            "query": query_params,
            "headers": dict(self.headers),
            "body": body.decode("utf-8")
        }
        
        self.server.requests.append(request_data)  # type: ignore
        
        status = getattr(self.server, "response_status", 200)  # type: ignore
        
        if status == 200:
            response = {}
            response_body = json.dumps(response).encode("utf-8")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        else:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()


class TelegramMockHandler(BaseHTTPRequestHandler):
    """HTTP-хендлер для имитации Telegram Bot API."""
    
    def log_message(self, format: str, *args: Any) -> None:
        """Подавляем логи сервера."""
        pass
    
    def do_POST(self) -> None:
        """Обработка POST-запросов."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        request_data = {
            "path": self.path,
            "headers": dict(self.headers),
            "body": body.decode("utf-8")
        }
        
        self.server.requests.append(request_data)  # type: ignore
        
        status = getattr(self.server, "response_status", 200)  # type: ignore
        
        if status == 200:
            response = {"ok": True, "result": {"message_id": 12345}}
            response_body = json.dumps(response).encode("utf-8")
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        else:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()


class MaxMockServer:
    """Контекстный менеджер для локального Max API сервера."""
    
    def __init__(self) -> None:
        self.port = _get_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.requests: list[dict] = []
        self.response_status = 200
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
    
    def __enter__(self) -> "MaxMockServer":
        """Запуск сервера."""
        self.server = HTTPServer(("127.0.0.1", self.port), MaxMockHandler)
        self.server.requests = self.requests  # type: ignore
        self.server.response_status = self.response_status  # type: ignore
        
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Остановка сервера."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)
    
    def set_response_status(self, status: int) -> None:
        """Установить HTTP статус для следующих ответов."""
        self.response_status = status
        if self.server:
            self.server.response_status = status  # type: ignore


class TelegramMockServer:
    """Контекстный менеджер для локального Telegram API сервера."""
    
    def __init__(self) -> None:
        self.port = _get_free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.requests: list[dict] = []
        self.response_status = 200
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None
    
    def __enter__(self) -> "TelegramMockServer":
        """Запуск сервера."""
        self.server = HTTPServer(("127.0.0.1", self.port), TelegramMockHandler)
        self.server.requests = self.requests  # type: ignore
        self.server.response_status = self.response_status  # type: ignore
        
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Остановка сервера."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread:
            self.thread.join(timeout=1.0)
    
    def set_response_status(self, status: int) -> None:
        """Установить HTTP статус для следующих ответов."""
        self.response_status = status
        if self.server:
            self.server.response_status = status  # type: ignore


class FakeConfig:
    """Минимальная имитация конфига."""
    
    def __init__(self, **kwargs: Any) -> None:
        self._data = kwargs
    
    def get(self, key: str, default: Any = None) -> Any:
        """Получить значение конфига."""
        return self._data.get(key, default)


class FakeStore:
    """Минимальная имитация store для дебаунса."""
    
    def __init__(self) -> None:
        self.events: set[str] = set()
    
    def append_event(self, event_in: Any) -> tuple[Any, bool]:
        """
        Записать событие с дедупликацией по dedup_key.
        
        Returns:
            (event_id, created) где created=False если ключ уже был
        """
        dedup_key = getattr(event_in, "dedup_key", None)
        
        if dedup_key in self.events:
            return (None, False)
        
        self.events.add(dedup_key)
        return (len(self.events), True)


def test_channel_max_отправляет_только_в_max():
    """channel=max: сообщение уходит только на Max, Telegram не дёргается."""
    with MaxMockServer() as max_server, TelegramMockServer() as tg_server:
        os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_tg_token_456"
        
        try:
            config = FakeConfig(
                **{
                    "notify.channel": "max",
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "987654321",
                    "notify.max_api_base": max_server.base_url,
                    "notify.token_env": "TELEGRAM_BOT_TOKEN",
                    "notify.ops_chat_id": "123456789",
                    "notify.api_base": tg_server.base_url,
                }
            )
            
            notifier = Notifier(config)
            
            result = notifier.notify(
                "warm_lead_created",
                {"note": "Тестовое сообщение"},
                now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
            )
            
            assert result is True
            assert len(max_server.requests) == 1
            assert len(tg_server.requests) == 0
            
            max_req = max_server.requests[0]
            assert max_req["path"] == "/messages"
            assert max_req["query"]["chat_id"] == ["987654321"]
            assert max_req["headers"]["Authorization"] == "test_max_token_123"
            
            body = json.loads(max_req["body"])
            assert body["format"] == "html"
            assert body["notify"] is True
            assert "Тестовое сообщение" in body["text"]
        finally:
            os.environ.pop("MAX_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_channel_both_отправляет_в_оба_канала():
    """channel=both: сообщение уходит и в Max, и в Telegram."""
    with MaxMockServer() as max_server, TelegramMockServer() as tg_server:
        os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_tg_token_456"
        
        try:
            config = FakeConfig(
                **{
                    "notify.channel": "both",
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "987654321",
                    "notify.max_api_base": max_server.base_url,
                    "notify.token_env": "TELEGRAM_BOT_TOKEN",
                    "notify.ops_chat_id": "123456789",
                    "notify.api_base": tg_server.base_url,
                }
            )
            
            notifier = Notifier(config)
            
            result = notifier.notify(
                "warm_lead_created",
                {"note": "Тестовое сообщение"},
                now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
            )
            
            assert result is True
            assert len(max_server.requests) == 1
            assert len(tg_server.requests) == 1
        finally:
            os.environ.pop("MAX_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_channel_отсутствует_только_telegram():
    """Если channel не задан в конфиге, работает только Telegram (обратная совместимость)."""
    with MaxMockServer() as max_server, TelegramMockServer() as tg_server:
        os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_tg_token_456"
        
        try:
            config = FakeConfig(
                **{
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "987654321",
                    "notify.max_api_base": max_server.base_url,
                    "notify.token_env": "TELEGRAM_BOT_TOKEN",
                    "notify.ops_chat_id": "123456789",
                    "notify.api_base": tg_server.base_url,
                }
            )
            
            notifier = Notifier(config)
            
            result = notifier.notify(
                "warm_lead_created",
                {"note": "Тестовое сообщение"},
                now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
            )
            
            assert result is True
            assert len(tg_server.requests) == 1
            assert len(max_server.requests) == 0
        finally:
            os.environ.pop("MAX_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_channel_both_сбой_max_telegram_доставляется():
    """Сбой Max (500) при channel=both: Telegram всё равно получил сообщение, notify() вернул True."""
    with MaxMockServer() as max_server, TelegramMockServer() as tg_server:
        max_server.set_response_status(500)
        
        os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_tg_token_456"
        
        try:
            config = FakeConfig(
                **{
                    "notify.channel": "both",
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "987654321",
                    "notify.max_api_base": max_server.base_url,
                    "notify.token_env": "TELEGRAM_BOT_TOKEN",
                    "notify.ops_chat_id": "123456789",
                    "notify.api_base": tg_server.base_url,
                }
            )
            
            notifier = Notifier(config)
            
            result = notifier.notify(
                "warm_lead_created",
                {"note": "Тестовое сообщение"},
                now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
            )
            
            assert result is True
            # _send_max ретраит 5xx (retries=2) — запросов может быть до 3
            assert len(max_server.requests) >= 1
            assert len(tg_server.requests) == 1
        finally:
            os.environ.pop("MAX_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_channel_both_сбой_сети_max_telegram_доставляется():
    """Сбой сети Max (закрытый порт) при channel=both: Telegram получил, notify() вернул True."""
    with TelegramMockServer() as tg_server:
        os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
        os.environ["TELEGRAM_BOT_TOKEN"] = "test_tg_token_456"
        
        try:
            config = FakeConfig(
                **{
                    "notify.channel": "both",
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "987654321",
                    "notify.max_api_base": "http://127.0.0.1:9",
                    "notify.token_env": "TELEGRAM_BOT_TOKEN",
                    "notify.ops_chat_id": "123456789",
                    "notify.api_base": tg_server.base_url,
                }
            )
            
            notifier = Notifier(config)
            
            result = notifier.notify(
                "warm_lead_created",
                {"note": "Тестовое сообщение"},
                now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
            )
            
            assert result is True
            assert len(tg_server.requests) == 1
        finally:
            os.environ.pop("MAX_BOT_TOKEN", None)
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_channel_max_сбой_сети_возвращает_false():
    """Сбой сети Max (закрытый порт) при channel=max: notify() вернул False."""
    os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
    
    try:
        config = FakeConfig(
            **{
                "notify.channel": "max",
                "notify.max_token_env": "MAX_BOT_TOKEN",
                "notify.max_ops_chat_id": "987654321",
                "notify.max_api_base": "http://127.0.0.1:9",
            }
        )
        
        notifier = Notifier(config)
        
        result = notifier.notify(
            "warm_lead_created",
            {"note": "Тестовое сообщение"},
            now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)
        )
        
        assert result is False
    finally:
        os.environ.pop("MAX_BOT_TOKEN", None)


def test_дебаунс_общий_для_обоих_каналов():
    """Дебаунс применяется ДО доставки: второй вызов в окне не дёргает НИ один канал."""
    with TelegramMockServer() as tg_server, MaxMockServer() as max_server:
        os.environ["TEST_TG_TOKEN"] = "tg_token"
        os.environ["MAX_BOT_TOKEN"] = "max_token"
        try:
            config = FakeConfig(
                **{
                    "notify.channel": "both",
                    "notify.token_env": "TEST_TG_TOKEN",
                    "notify.ops_chat_id": "111",
                    "notify.api_base": tg_server.base_url,
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "222",
                    "notify.max_api_base": max_server.base_url,
                }
            )
            notifier = Notifier(config, store=FakeStore())
            now = datetime(2026, 7, 20, 12, 0, 0, tzinfo=timezone.utc)

            # complaint_rate_approaching_kill: окно дебаунса 1800с
            assert notifier.notify(
                "complaint_rate_approaching_kill", {"rate": "0.09"}, now=now,
            ) is True
            assert notifier.notify(
                "complaint_rate_approaching_kill", {"rate": "0.091"},
                now=datetime(2026, 7, 20, 12, 0, 30, tzinfo=timezone.utc),
            ) is False  # то же окно -> подавлено ДО каналов

            assert len(tg_server.requests) == 1
            assert len(max_server.requests) == 1
        finally:
            os.environ.pop("TEST_TG_TOKEN", None)
            os.environ.pop("MAX_BOT_TOKEN", None)

def test_channel_max_без_токена_disabled():
    """channel=max, но нет MAX_BOT_TOKEN в env -> notifier.disabled True."""
    config = FakeConfig(
        **{
            "notify.channel": "max",
            "notify.max_token_env": "NONEXISTENT_MAX_TOKEN",
            "notify.max_ops_chat_id": "987654321",
        }
    )
    
    notifier = Notifier(config)
    
    assert notifier.disabled is True


def test_max_обрезает_длинный_текст():
    """text длиннее 4000 символов -> в теле Max text обрезан до 4000.

    Проверяем прямой вызов _send_max: notify() сюда не дотянет длинный текст,
    т.к. _format_message режет значения payload до 200 символов ещё раньше.
    """
    with MaxMockServer() as max_server:
        os.environ["MAX_BOT_TOKEN"] = "test_max_token_123"
        try:
            config = FakeConfig(
                **{
                    "notify.channel": "max",
                    "notify.max_token_env": "MAX_BOT_TOKEN",
                    "notify.max_ops_chat_id": "987654321",
                    "notify.max_api_base": max_server.base_url,
                }
            )
            notifier = Notifier(config)
            assert notifier._send_max("987654321", "А" * 5000) is True
            assert len(max_server.requests) == 1
            body = json.loads(max_server.requests[0]["body"])
            assert len(body["text"]) == 4000
        finally:
            os.environ.pop("MAX_BOT_TOKEN", None)
