"""
HTTP-сервер для обработки запросов на отписку (RFC 8058 One-Click Unsubscribe).

Предоставляет публичный эндпоинт на трекинг-домене для обработки POST-запросов
от почтовых провайдеров и GET-запросов от пользователей.
"""

import argparse
import logging
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from html import escape as _html_escape  # локальные `html = f'...'` в
from urllib.parse import parse_qs, urlparse  # обработчиках затеняют модуль

# П3.2: потолок тела POST — one-click несёт пару десятков байт
# (List-Unsubscribe=One-Click); всё сильно больше — не наш клиент.
_MAX_POST_BODY = 1 * 1024 * 1024

from sender.config import Config
from sender.store import Store
from sender.suppression import Suppression
from sender.tracking import GIF_PIXEL, OpenTracker
from sender.unsub import Unsub, ValidationError

logger = logging.getLogger(__name__)


def make_server(
    config: Config,
    store: Store,
    suppression: Suppression,
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
) -> ThreadingHTTPServer:
    """
    Создать HTTP-сервер для обработки запросов на отписку.

    Args:
        config: Конфигурация приложения
        store: Хранилище данных
        suppression: Менеджер подавления рассылок
        host: Адрес для прослушивания
        port: Порт для прослушивания

    Returns:
        Настроенный экземпляр ThreadingHTTPServer
    """
    unsub = Unsub(config, store, suppression)
    unsub_path = config.get("unsub.path", "/u")
    legal = config.legal()
    # open-tracking: пиксель /o/<token> живёт на том же трекинг-домене
    tracker = OpenTracker(config, store)
    track_path = "/" + str(config.get("tracking.path", "/o")).strip("/")

    class UnsubRequestHandler(BaseHTTPRequestHandler):
        """Обработчик HTTP-запросов для эндпоинта отписки."""

        server_version = "UnsubServer/1.0"
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args) -> None:
            """Переопределение логирования для использования logging вместо stderr."""
            logger.info(
                "%s - - %s",
                self.address_string(),
                format % args,
            )

        def _parse_token(self) -> Optional[str]:
            """
            Извлечь токен из query-параметра t.

            Returns:
                Токен или None, если параметр отсутствует
            """
            parsed = urlparse(self.path)
            query_params = parse_qs(parsed.query)
            tokens = query_params.get("t", [])
            return tokens[0] if tokens else None

        def _get_accept_header(self) -> str:
            """Получить значение заголовка Accept."""
            return self.headers.get("Accept", "")

        def _send_response_text(self, code: int, message: str) -> None:
            """
            Отправить текстовый ответ.

            Args:
                code: HTTP-код ответа
                message: Тело ответа
            """
            self.send_response(code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(message.encode("utf-8"))

        def _send_response_html(self, code: int, html: str) -> None:
            """
            Отправить HTML-ответ.

            Args:
                code: HTTP-код ответа
                html: HTML-содержимое
            """
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        def _handle_one_click_post(self, token: str) -> None:
            """
            Обработать POST-запрос One-Click отписки (RFC 8058).

            Args:
                token: Токен отписки из query-параметра
            """
            try:
                result = unsub.handle_one_click(token)

                # П1.4: сначала проверяем результат, потом отвечаем. Раньше
                # 200 «Вы отписаны» уходил ДО проверки result.ok — провайдер
                # считал отписку выполненной, хотя в suppression ничего не
                # попало (получатель не найден).
                if not result.ok:
                    logger.warning(
                        "One-click unsubscribe failed: recipient %s not found",
                        result.recipient_id,
                    )
                    self._send_response_text(404, "Unsubscribe link is not valid")
                    return

                accept = self._get_accept_header()
                if "text/html" in accept.lower():
                    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Отписка выполнена</title>
</head>
<body>
    <h1>Вы отписаны</h1>
    <p>Вы больше не будете получать рассылки.</p>
    <hr>
    <p><small>{legal.entity}</small></p>
</body>
</html>"""
                    self._send_response_html(200, html)
                else:
                    self._send_response_text(200, "OK")

                logger.info(
                    "One-click unsubscribe successful: recipient_id=%s",
                    result.recipient_id,
                )

            except ValidationError as e:
                logger.warning("Invalid unsubscribe token: %s", e)
                self._send_response_text(400, "Invalid token")
            except Exception as e:
                logger.exception("Error processing one-click unsubscribe")
                self._send_response_text(500, "error")

        def _handle_unsub_get(self, token: str) -> None:
            """
            Отобразить страницу отписки для пользователя.

            Args:
                token: Токен отписки из query-параметра
            """
            try:
                html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Отписка от рассылки</title>
    <style>
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            max-width: 600px;
            margin: 50px auto;
            padding: 20px;
            line-height: 1.6;
        }}
        .card {{
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 30px;
            background: #f9f9f9;
        }}
        h1 {{
            margin-top: 0;
            color: #333;
        }}
        button {{
            background: #d32f2f;
            color: white;
            border: none;
            padding: 12px 24px;
            font-size: 16px;
            border-radius: 4px;
            cursor: pointer;
            margin-top: 20px;
        }}
        button:hover {{
            background: #b71c1c;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            font-size: 14px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Отписка от рассылки</h1>
        <p>Вы больше не будете получать письма от нас.</p>
        <form method="POST" action="?t={_html_escape(token, quote=True)}">
            <button type="submit">Отписаться</button>
        </form>
        <div class="footer">
            {legal.entity}
        </div>
    </div>
</body>
</html>"""
                self._send_response_html(200, html)
            except Exception as e:
                logger.exception("Error rendering unsubscribe page")
                self._send_response_text(500, "error")

        def do_GET(self) -> None:
            """Обработать GET-запрос."""
            try:
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/health":
                    self._send_response_text(200, "ok")
                    return

                if path == unsub_path:
                    token = self._parse_token()
                    if not token:
                        self._send_response_text(400, "Missing token parameter")
                        return

                    self._handle_unsub_get(token)
                    return

                # Пиксель открытий: /o/<token>. ВСЕГДА 200 + GIF (и на битый
                # токен — не палим клиенту валидацию), кэш выключен.
                if path.startswith(track_path + "/"):
                    token = path[len(track_path):].strip("/")
                    try:
                        tracker.record_open(token)
                    except Exception:  # noqa: BLE001 - пиксель не должен падать
                        logger.exception("open-tracking record failed")
                    self.send_response(200)
                    self.send_header("Content-Type", "image/gif")
                    self.send_header("Content-Length", str(len(GIF_PIXEL)))
                    self.send_header(
                        "Cache-Control", "no-store, no-cache, must-revalidate")
                    self.end_headers()
                    self.wfile.write(GIF_PIXEL)
                    return

                self._send_response_text(404, "Not Found")

            except Exception as e:
                logger.exception("Unexpected error in GET handler")
                self._send_response_text(500, "error")

        def do_POST(self) -> None:
            """Обработать POST-запрос."""
            try:
                parsed = urlparse(self.path)
                path = parsed.path

                if path == unsub_path:
                    token = self._parse_token()
                    if not token:
                        self._send_response_text(400, "Missing token parameter")
                        return

                    # П3.2: Content-Length с мусором раньше ронял int() в общий
                    # except (невнятный 500), а огромное значение блокировало
                    # поток на rfile.read() — DoS на ThreadingHTTPServer.
                    try:
                        content_length = int(self.headers.get("Content-Length", 0))
                    except (TypeError, ValueError):
                        self._send_response_text(400, "Bad Content-Length")
                        return
                    if content_length > _MAX_POST_BODY:
                        self._send_response_text(413, "Payload Too Large")
                        return
                    if content_length > 0:
                        self.rfile.read(content_length)

                    self._handle_one_click_post(token)
                    return

                self._send_response_text(404, "Not Found")

            except Exception as e:
                logger.exception("Unexpected error in POST handler")
                self._send_response_text(500, "error")

    server = ThreadingHTTPServer((host, port), UnsubRequestHandler)
    logger.info("Unsub server listening on %s:%d", host, port)
    return server


def run_unsub_server(
    config: Config,
    store: Store,
    suppression: Suppression,
    *,
    host: str = "0.0.0.0",
    port: int = 8080,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    Запустить HTTP-сервер отписки в текущем потоке.

    Args:
        config: Конфигурация приложения
        store: Хранилище данных
        suppression: Менеджер подавления рассылок
        host: Адрес для прослушивания
        port: Порт для прослушивания
        stop_event: Событие для остановки сервера (опционально)
    """
    server = make_server(config, store, suppression, host=host, port=port)

    if stop_event is not None:

        def shutdown_on_event():
            """Ожидать события и остановить сервер."""
            stop_event.wait()
            logger.info("Stop event received, shutting down server")
            server.shutdown()

        shutdown_thread = threading.Thread(target=shutdown_on_event, daemon=True)
        shutdown_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, shutting down")
    finally:
        server.server_close()


def main(argv: Optional[list[str]] = None) -> int:
    """
    Точка входа для запуска сервера отписки.

    Args:
        argv: Аргументы командной строки (по умолчанию sys.argv)

    Returns:
        Код возврата (0 при успехе)
    """
    parser = argparse.ArgumentParser(
        description="HTTP-сервер обработки запросов на отписку (RFC 8058)"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Путь к файлу конфигурации",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Адрес для прослушивания (по умолчанию 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Порт для прослушивания (по умолчанию 8080)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Уровень логирования",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        config = Config.load(args.config)
        db_path = config.get("db.path")
        if not db_path:
            logger.error("db.path not configured")
            return 1

        store = Store(db_path)
        suppression = Suppression(store)

        run_unsub_server(
            config,
            store,
            suppression,
            host=args.host,
            port=args.port,
        )

        return 0

    except Exception as e:
        logger.exception("Failed to start unsub server: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
