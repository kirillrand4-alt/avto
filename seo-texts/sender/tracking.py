"""
Open-tracking (пиксель открытий писем).

Отдаёт 1x1 GIF на трекинг-домене, кодирует message_id в подписанный токен
(тот же HMAC-секрет, что и unsub), пишет событие 'open' при загрузке пикселя.

ВАЖНО (оговорка владельца): 74% базы — Mail.ru/Яндекс, они проксируют картинки.
Открытие либо не считается (картинки выключены), либо накручивается провайдером
(антиспам-префетч грузит пиксель без участия человека). Поэтому open —
СПРАВОЧНЫЙ сигнал, НЕ основа решений. Гейты каденции/приоритеты ведём по
ответу/клику. Здесь только фиксируем факт загрузки пикселя с отсевом префетча.
"""

import base64
import hashlib
import hmac
import html
import json
import os
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .config import Config
    from .store import Store


# Тип события открытия — отдельная константа, чтобы не подмешивать в bounce/complaint.
EVENT_OPEN = "open"

# Валидный прозрачный GIF89a 1x1, 43 байта. Отдаём его на любой запрос /o/<token>
# (даже на битый токен), чтобы не палить клиенту факт валидации.
GIF_PIXEL: bytes = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00"
    b"!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
    b"\x00\x00\x02\x02D\x01\x00;"
)


class TrackTokenError(Exception):
    """Битый или неверно подписанный трекинг-токен."""


class OpenTracker:
    """
    Генерация/проверка трекинг-токенов и запись событий открытия.

    Токен кодирует message_id (+recipient_id, campaign_id) и подписан HMAC-SHA256
    на том же секрете, что unsub. Запись открытия дедуплицируется по message_id
    (первое открытие на письмо), провайдер-префетч отсекается по возрасту письма.
    """

    def __init__(self, config: "Config", store: "Store"):
        self._config = config
        self._store = store

        legal = config.legal()
        secret_env = legal.unsub_secret_env
        secret = os.environ.get(secret_env)
        if not secret:
            raise ValueError(f"Missing environment variable: {secret_env}")
        self._secret = secret.encode("utf-8")

        # Трекинг-домен — тот же, что unsub_base_url (или явный поддомен из конфига).
        base = config.get("tracking.base_url", "") or legal.unsub_base_url
        self._base_url = base.rstrip("/")

    def make_token(self, message_id: int, recipient_id: int, campaign_id: int) -> str:
        """
        Подписанный токен для письма.

        Формат: base64url(payload_json).base64url(hmac) без паддинга — как в unsub.
        Payload и подпись кодируются отдельно ради понятной диагностики ошибок.
        """
        ts = int(datetime.now(timezone.utc).timestamp())
        payload = {"mid": message_id, "rid": recipient_id, "cid": campaign_id, "ts": ts}
        # P2 №2: единое ядро подписанных токенов (общее с unsub)
        from sender.tokens import sign_token
        return sign_token(self._secret, payload)

    def verify_token(self, token: str) -> dict:
        """
        Проверить подпись токена и вернуть payload (mid/rid/cid/ts).

        Ядро — sender.tokens.verify_token (P2 №2: механизм общий с unsub);
        причины отказа те же, наружу — TrackTokenError этого модуля.
        """
        from sender.tokens import TokenError, verify_token
        try:
            return verify_token(self._secret, token,
                                required_int_fields=("mid", "rid", "cid", "ts"))
        except TokenError as e:
            raise TrackTokenError(str(e))

    def pixel_url(self, token: str) -> str:
        """URL пикселя: {base}/o/{token}. Путь конфигурируем (tracking.path)."""
        path = self._config.get("tracking.path", "/o")
        path = "/" + path.strip("/")
        return f"{self._base_url}{path}/{token}"

    def record_open(
        self,
        token: str,
        *,
        now: Optional[datetime] = None,
        min_age_sec: Optional[int] = None,
    ) -> bool:
        """
        Записать открытие по токену пикселя.

        Возвращает True только если событие реально создано (первое открытие).
        False во всех остальных случаях, БЕЗ исключений наружу:
        - битый/поддельный токен;
        - письмо не найдено или ещё не отправлено (sent_at None);
        - префетч-отсев: письмо младше min_age_sec (провайдер грузит пиксель сам);
        - повторное открытие (дедуп по dedup_key=open:<mid>).
        """
        try:
            payload = self.verify_token(token)
        except TrackTokenError:
            # Наружу отдаём GIF+200, событие просто не пишем.
            return False

        mid = payload["mid"]
        message = self._store.get_message(mid)
        if message is None:
            return False
        if message.sent_at is None:
            return False

        if now is None:
            now = datetime.now(timezone.utc)
        if min_age_sec is None:
            min_age_sec = self._config.get("tracking.min_age_sec", 3)

        # Нормализуем время: sent_at может быть naive -> считаем UTC.
        sent_at = message.sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        now_norm = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)

        # Префетч-отсев: слишком быстрый запрос после отправки — это не человек.
        age_sec = (now_norm - sent_at).total_seconds()
        if age_sec < min_age_sec:
            return False

        from .store import EventIn

        _id, created = self._store.append_event(
            EventIn(
                dedup_key=f"open:{mid}",
                event_type=EVENT_OPEN,
                event_ts=now_norm,
                message_id=mid,
                recipient_id=message.recipient_id,
                campaign_id=message.campaign_id,
                mailbox_id=message.mailbox_id,
            )
        )
        return created

    def enabled_for(self, campaign) -> bool:
        """
        Включён ли open-tracking для кампании.

        Глобальный флаг tracking.open_enabled (по умолчанию False) И
        per-campaign флаг open_tracking (по умолчанию True). Кампания без .config
        (None/отсутствует) считается разрешённой при включённом глобальном флаге.
        """
        if not self._config.get("tracking.open_enabled", False):
            return False
        if campaign is None:
            return True
        cfg = getattr(campaign, "config", None)
        if not cfg:
            return True
        return cfg.get("open_tracking", True) is not False


def text_to_html(body: str) -> str:
    """
    Обернуть простой текст в минимальный HTML.

    Экранируем спецсимволы, переносы строк -> <br>, оборачиваем в pre-wrap div,
    чтобы сохранить исходное форматирование без украшательств.
    """
    escaped = html.escape(body)
    escaped = escaped.replace("\n", "<br>")
    return (
        "<html><body>"
        '<div style="white-space:pre-wrap; font-family:inherit">'
        f"{escaped}"
        "</div></body></html>"
    )


# Регистронезависимый поиск закрывающего </body> для вставки пикселя перед ним.
_BODY_CLOSE_RE = re.compile(r"</body\s*>", re.IGNORECASE)


def inject_pixel(html_body: str, pixel_url: str) -> str:
    """
    Вставить трекинг-пиксель перед </body>.

    Скрытый 1x1 img. Если </body> нет — дописываем пиксель в конец документа.
    """
    img = (
        f'<img src="{pixel_url}" width="1" height="1" alt="" '
        'style="display:none">'
    )
    match = _BODY_CLOSE_RE.search(html_body)
    if match is None:
        return html_body + img
    idx = match.start()
    return html_body[:idx] + img + html_body[idx:]
