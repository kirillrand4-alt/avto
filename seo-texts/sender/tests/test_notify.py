"""Unit tests for sender.notify.

Использует локальный http.server на 127.0.0.1 со свободным портом для имитации
Telegram Bot API. Все сетевые вызовы направляются на локальный сервер.
Дебаунс проверяется через минимальный FakeStore.
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


class TelegramMockHandler(BaseHTTPRequestHandler):
    """HTTP-хендлер для имитации Telegram Bot API."""
    
    def log_message(self, format: str, *args: Any) -> None:
        """Подавляем логи сервера."""
        pass
    
    def do_POST(self) -> None:
        """Обработка POST-запросов."""
        # Читаем тело запроса
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        
        # Сохраняем запрос
        request_data = {
            "path": self.path,
            "headers": dict(self.headers),
            "body": body.decode("utf-8")
        }
        
        # Добавляем в список запросов сервера
        self.server.requests.append(request_data)  # type: ignore
        
        # Определяем ответ
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
            # Ключ уже существует
            return (None, False)
        
        # Новый ключ
        self.events.add(dedup_key)
        return (len(self.events), True)


# ============================================================================
# Тесты disabled режима
# ============================================================================


def test_disabled_без_токена():
    """Notifier без токена работает в disabled режиме, notify возвращает False."""
    config = FakeConfig(
        **{
            "notify.token_env": "NONEXISTENT_TOKEN_VAR",
            "notify.ops_chat_id": "123456789",
        }
    )
    
    notifier = Notifier(config)
    
    assert notifier.disabled is True
    
    result = notifier.notify("kill_switch_triggered", {"foo": "bar"})
    assert result is False


def test_disabled_без_ops_chat():
    """Notifier без ops_chat_id работает в disabled режиме."""
    config = FakeConfig(**{"notify.token_env": "TELEGRAM_BOT_TOKEN"})
    
    # Устанавливаем токен в окружение
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
    
    try:
        notifier = Notifier(config)
        
        assert notifier.disabled is True
        
        result = notifier.notify("kill_switch_triggered", {"foo": "bar"})
        assert result is False
    finally:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)


def test_disabled_digest():
    """Метод digest в disabled режиме возвращает False."""
    config = FakeConfig(
        **{
            "notify.token_env": "NONEXISTENT_TOKEN_VAR",
            "notify.ops_chat_id": "123456789",
        }
    )
    
    notifier = Notifier(config)
    
    result = notifier.digest({"sent": 100, "delivered": 95})
    assert result is False


# ============================================================================
# Тесты happy path
# ============================================================================


def test_happy_path_отправка_в_ops_chat():
    """Успешная отправка P2 события в ops_chat через локальный сервер."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-1001234567890",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "test_bot_token_123"
        
        try:
            notifier = Notifier(config)
            
            assert notifier.disabled is False
            
            now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "complaint_rate_approaching_kill",
                {"rate": "0.09", "threshold": "0.1"},
                now=now,
            )
            
            assert result is True
            assert len(server.requests) == 1
            
            req = server.requests[0]
            assert req["path"] == "/bottest_bot_token_123/sendMessage"
            assert req["headers"]["Content-Type"] == "application/json"
            
            body = json.loads(req["body"])
            assert body["chat_id"] == "-1001234567890"
            assert "parse_mode" in body
            assert body["parse_mode"] == "HTML"
            assert "disable_web_page_preview" in body
            
            text = body["text"]
            assert "🟠" in text
            assert "P2" in text
            assert "complaint_rate_approaching_kill" in text
            assert "rate: 0.09" in text
            assert "threshold: 0.1" in text
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_happy_path_kill_switch_в_оба_чата():
    """P1 событие kill_switch_triggered отправляется и в ops, и в oncall."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100111",
                "notify.oncall_chat_id": "-100222",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "bot_token"
        
        try:
            notifier = Notifier(config)
            
            now = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "kill_switch_triggered",
                {"metric": "global_bounce_rate", "value": "0.12"},
                now=now,
            )
            
            assert result is True
            assert len(server.requests) == 2
            
            # Первый запрос - в ops_chat
            req1 = server.requests[0]
            body1 = json.loads(req1["body"])
            assert body1["chat_id"] == "-100111"
            
            text1 = body1["text"]
            assert "🔴" in text1
            assert "P1" in text1
            assert "kill_switch_triggered" in text1
            
            # Второй запрос - в oncall_chat
            req2 = server.requests[1]
            body2 = json.loads(req2["body"])
            assert body2["chat_id"] == "-100222"
            
            # Текст должен быть тот же
            assert body2["text"] == text1
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_happy_path_p3_событие():
    """P3 событие отправляется с ℹ️ эмодзи."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100333",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            # 12:00 по Москве (UTC+3) = 09:00 UTC
            now = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "unknown_event_type", {"info": "test"}, now=now
            )
            
            assert result is True
            assert len(server.requests) == 1
            
            body = json.loads(server.requests[0]["body"])
            text = body["text"]
            
            assert "ℹ️" in text
            assert "P3" in text
            assert "unknown_event_type" in text
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_happy_path_digest():
    """Метод digest отправляет дневную сводку."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100444",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            stats = {
                "sent": 10000,
                "delivered": 9500,
                "bounced": 300,
                "complained": 20,
            }
            
            result = notifier.digest(stats)
            
            assert result is True
            assert len(server.requests) == 1
            
            body = json.loads(server.requests[0]["body"])
            assert body["chat_id"] == "-100444"
            
            text = body["text"]
            assert "ℹ️" in text
            assert "P3" in text
            assert "Дневная сводка" in text
            assert "sent: 10000" in text
            assert "delivered: 9500" in text
        finally:
            os.environ.pop("TEST_TOKEN", None)


# ============================================================================
# Тесты дебаунса
# ============================================================================


def test_debounce_дубликат_в_окне():
    """Повторное событие в окне дебаунса пропускается."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100555",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        store = FakeStore()
        
        try:
            notifier = Notifier(config, store=store)
            
            now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            
            # Первая отправка
            result1 = notifier.notify(
                "complaint_rate_approaching_kill",
                {"rate": "0.09"},
                now=now,
            )
            
            assert result1 is True
            assert len(server.requests) == 1
            
            # Повторная отправка через 10 минут (в том же 30-минутном окне)
            now2 = now + timedelta(minutes=10)
            result2 = notifier.notify(
                "complaint_rate_approaching_kill",
                {"rate": "0.095"},
                now=now2,
            )
            
            assert result2 is False
            assert len(server.requests) == 1  # Нет новых запросов
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_debounce_новое_окно():
    """Событие в новом окне дебаунса отправляется."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100666",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        store = FakeStore()
        
        try:
            notifier = Notifier(config, store=store)
            
            now1 = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
            
            result1 = notifier.notify(
                "smtp_persistent_failure",
                {"mailbox": "user@example.com"},
                now=now1,
            )
            
            assert result1 is True
            assert len(server.requests) == 1
            
            # Через 61 минуту - новое окно (окно 3600 сек = 1 час)
            now2 = now1 + timedelta(minutes=61)
            result2 = notifier.notify(
                "smtp_persistent_failure",
                {"mailbox": "user@example.com"},
                now=now2,
            )
            
            assert result2 is True
            assert len(server.requests) == 2
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_debounce_kill_switch_без_дебаунса():
    """kill_switch_triggered имеет окно 0, всегда отправляется даже при store."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100777",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        store = FakeStore()
        
        try:
            notifier = Notifier(config, store=store)
            
            now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
            
            # Три отправки подряд
            for i in range(3):
                result = notifier.notify(
                    "kill_switch_triggered",
                    {"metric": "bounce", "value": "0.15"},
                    now=now + timedelta(seconds=i),
                )
                assert result is True
            
            # Все три должны отправиться (kill_switch без дебаунса)
            # Каждое в ops + oncall не настроен, так что 3 запроса
            assert len(server.requests) == 3
            
            # Проверим, что dedup_key НЕ записывался в store
            # (т.к. окно 0 означает пропуск дебаунс-логики)
            assert len(store.events) == 0
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_debounce_без_store():
    """Без store дебаунс не работает, все события отправляются."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100888",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config, store=None)
            
            now = datetime(2025, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
            
            # Две отправки подряд с дебаунс-событием
            result1 = notifier.notify(
                "provider_bounce_trip", {"provider": "gmail"}, now=now
            )
            
            result2 = notifier.notify(
                "provider_bounce_trip",
                {"provider": "gmail"},
                now=now + timedelta(seconds=5),
            )
            
            assert result1 is True
            assert result2 is True
            assert len(server.requests) == 2
        finally:
            os.environ.pop("TEST_TOKEN", None)


# ============================================================================
# Тесты тихих часов
# ============================================================================


def test_quiet_hours_p3_ночью():
    """P3 событие в 23:00 МСК (20:00 UTC) пропускается."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-100999",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            # 23:00 МСК = 20:00 UTC
            now = datetime(2025, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "unknown_p3_event", {"info": "test"}, now=now
            )
            
            assert result is False
            assert len(server.requests) == 0
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_quiet_hours_p3_днём():
    """P3 событие в 12:00 МСК (09:00 UTC) отправляется."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101000",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            # 12:00 МСК = 09:00 UTC
            now = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "unknown_p3_event", {"info": "test"}, now=now
            )
            
            assert result is True
            assert len(server.requests) == 1
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_quiet_hours_p1_всегда_отправляется():
    """P1 событие отправляется в любое время, включая тихие часы."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101111",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            # 23:00 МСК = 20:00 UTC (тихие часы для P3)
            now = datetime(2025, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "kill_switch_triggered", {"metric": "bounce"}, now=now
            )
            
            assert result is True
            assert len(server.requests) == 1
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_quiet_hours_p2_всегда_отправляется():
    """P2 событие отправляется в любое время."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101222",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            # 02:00 МСК = 23:00 предыдущего дня UTC
            now = datetime(2025, 1, 14, 23, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "complaint_rate_approaching_kill", {"rate": "0.09"}, now=now
            )
            
            assert result is True
            assert len(server.requests) == 1
        finally:
            os.environ.pop("TEST_TOKEN", None)


# ============================================================================
# Тесты форматирования сообщений
# ============================================================================


def test_format_warm_lead_с_card_url():
    """warm_lead_created включает card_url как ссылку."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101333",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            now = datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "warm_lead_created",
                {
                    "lead_id": "abc123",
                    "card_url": "https://crm.example.com/lead/abc123",
                },
                now=now,
            )
            
            assert result is True
            assert len(server.requests) == 1
            
            body = json.loads(server.requests[0]["body"])
            text = body["text"]
            
            assert "warm_lead_created" in text
            assert "lead_id: abc123" in text
            assert "card_url: https://crm.example.com/lead/abc123" in text
            assert '<a href="https://crm.example.com/lead/abc123">Открыть карточку</a>' in text
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_format_html_экранирование():
    """HTML-спецсимволы экранируются в значениях payload."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101444",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            now = datetime(2025, 1, 15, 11, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "test_event",
                {"message": "<script>alert('xss')</script> & stuff"},
                now=now,
            )
            
            assert result is True
            
            body = json.loads(server.requests[0]["body"])
            text = body["text"]
            
            assert "&lt;script&gt;" in text
            assert "&amp;" in text
            assert "<script>" not in text
            assert "alert('xss')" in text  # Одинарные кавычки не экранируются
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_format_длинные_значения_обрезаются():
    """Значения payload длиннее 200 символов обрезаются."""
    with TelegramMockServer() as server:
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101555",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            now = datetime(2025, 1, 15, 13, 0, 0, tzinfo=timezone.utc)
            
            long_value = "x" * 250
            
            result = notifier.notify(
                "test_event", {"data": long_value}, now=now
            )
            
            assert result is True
            
            body = json.loads(server.requests[0]["body"])
            text = body["text"]
            
            # Должно быть обрезано до 197 + "..."
            assert "x" * 197 in text
            assert "..." in text
            assert len(text) < len(long_value)
        finally:
            os.environ.pop("TEST_TOKEN", None)


# ============================================================================
# Тесты обработки ошибок
# ============================================================================


def test_error_http_500_с_ретраями():
    """Сервер возвращает 500, notifier делает ретраи и возвращает False."""
    with TelegramMockServer() as server:
        server.set_response_status(500)
        
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101666",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            now = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "kill_switch_triggered", {"metric": "bounce"}, now=now
            )
            
            assert result is False
            
            # Должно быть 3 попытки (initial + 2 retries)
            assert len(server.requests) == 3
        finally:
            os.environ.pop("TEST_TOKEN", None)


def test_error_http_400_без_ретраев():
    """Сервер возвращает 400, notifier не делает ретраи."""
    with TelegramMockServer() as server:
        server.set_response_status(400)
        
        config = FakeConfig(
            **{
                "notify.token_env": "TEST_TOKEN",
                "notify.ops_chat_id": "-101777",
                "notify.api_base": server.base_url,
            }
        )
        
        os.environ["TEST_TOKEN"] = "token"
        
        try:
            notifier = Notifier(config)
            
            now = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
            
            result = notifier.notify(
                "test_event", {"data": "test"}, now=now
            )
            
            assert result is False
            
            # Только одна попытка (4xx не ретраится)
            assert len(server.requests) == 1
        finally:
            os.environ.pop("TEST_TOKEN", None)
