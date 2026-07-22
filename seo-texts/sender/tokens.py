"""Единое ядро подписанных токенов (P2 №2): unsub и tracking делили дословно
одинаковый формат ``base64url(payload_json).base64url(hmac_sha256)`` на одном
секрете — теперь формат живёт в одном месте, модули лишь заворачивают ошибки
в свои классы (у токена отписки и пикселя разная СЕМАНТИКА, но один механизм).

Тексты ошибок сохранены дословно (их проверяют существующие тесты unsub).
"""

import base64
import hashlib
import hmac
import json
from typing import Any


class TokenError(Exception):
    """Битый или неверно подписанный токен (нейтральное ядро)."""


def sign_token(secret: bytes, payload: dict[str, Any]) -> str:
    """Подписать payload: canonical JSON + HMAC-SHA256, base64url без паддинга."""
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    sig = hmac.new(secret, payload_json.encode("utf-8"), hashlib.sha256).digest()
    p64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).rstrip(b"=").decode("ascii")
    s64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{p64}.{s64}"


def verify_token(secret: bytes, token: str, *,
                 required_int_fields: tuple[str, ...]) -> dict[str, Any]:
    """Проверить подпись и структуру токена; вернуть payload.

    Каждый режим отказа — TokenError со СТАБИЛЬНЫМ текстом (обёртки модулей
    транслируют его в свой класс, тесты сообщений не ломаются):
    формат / base64 / UTF-8 / JSON / поля / подпись (constant-time).
    """
    parts = token.split(".", 1)
    if len(parts) != 2:
        raise TokenError("Token format invalid")
    payload_b64, sig_b64 = parts

    try:
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception as e:  # noqa: BLE001
        raise TokenError(f"Invalid base64: {e}")

    try:
        payload_str = payload_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise TokenError(f"Invalid UTF-8 in token: {e}")

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as e:
        raise TokenError(f"Invalid JSON payload: {e}")
    if not isinstance(payload, dict):
        raise TokenError("Payload must be dict")

    for key in required_int_fields:
        value = payload.get(key)
        # bool — подтип int, но валидное поле токена им быть не может
        if not isinstance(value, int) or isinstance(value, bool):
            raise TokenError(f"Missing or invalid field: {key}")

    try:
        s_padded = sig_b64 + "=" * ((4 - len(sig_b64) % 4) % 4)
        sig_bytes = base64.urlsafe_b64decode(s_padded.encode("ascii"))
    except Exception as e:  # noqa: BLE001
        raise TokenError(f"Invalid base64: {e}")

    canonical_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    expected = hmac.new(secret, canonical_json.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(sig_bytes, expected):
        raise TokenError("Signature mismatch")

    return payload
