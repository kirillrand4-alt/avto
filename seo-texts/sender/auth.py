"""Аутентификация веб-панели: пароли, 2FA (TOTP), серверные сессии, роли.

BUILD-NEW для Фазы 2.1. ТОЛЬКО stdlib — намеренно без pyjwt/passlib/bcrypt
(инвариант проекта «движок на stdlib» + в этом окружении cryptography._rust
падает). Пароли — pbkdf2_hmac(sha256); 2FA — TOTP по RFC 6238 на hmac-sha1;
сессии — opaque-токен (secrets), в БД лежит только его sha256 (сам токен не
хранится), отзыв через флаг ``revoked``.

Роли: owner (полный доступ) и manager (лид-деск). Единственный писатель в БД —
``store``; auth оркеструет его user/session-методы.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from sender.errors import SenderError  # noqa: E402

logger = logging.getLogger("sender.auth")


class AuthError(SenderError):
    """Ошибка аутентификации/авторизации."""


ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
_ROLES = {ROLE_OWNER, ROLE_MANAGER}

_PBKDF2_ITERS = 240_000
_SESSION_TTL_HOURS = 720   # 30 дней: оператор не переавторизуется каждый день
# (было 12ч — жаловались на постоянный релогин; localStorage хранит токен,
#  так что при живой сессии перезагрузка браузера не разлогинивает)


# --------------------------------------------------------------------------- #
# Пароли (pbkdf2_hmac sha256)
# --------------------------------------------------------------------------- #

def hash_password(password: str, *, iters: int = _PBKDF2_ITERS) -> str:
    """→ строка ``pbkdf2$<iters>$<salt_hex>$<hash_hex>`` (self-describing)."""
    if not password:
        raise AuthError("empty password")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
    return f"pbkdf2${iters}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time проверка пароля против хранимого ``pbkdf2$...``."""
    try:
        algo, iters_s, salt_hex, hash_hex = stored.split("$", 3)
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# --------------------------------------------------------------------------- #
# TOTP (RFC 6238, hmac-sha1) — совместим с Google Authenticator и т.п.
# --------------------------------------------------------------------------- #

def generate_totp_secret() -> str:
    """Случайный base32-секрет (без padding) для привязки в приложении-аутентификаторе."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    pad = "=" * (-len(secret_b32) % 8)
    key = base64.b32decode(secret_b32.upper() + pad)
    msg = struct.pack(">Q", counter)
    dig = hmac.new(key, msg, hashlib.sha1).digest()
    off = dig[-1] & 0x0F
    code = (struct.unpack(">I", dig[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp_now(secret_b32: str, *, period: int = 30, at: Optional[float] = None) -> str:
    ts = time.time() if at is None else at
    return _hotp(secret_b32, int(ts // period))


def verify_totp(secret_b32: str, code: str, *, window: int = 1,
                period: int = 30, at: Optional[float] = None) -> bool:
    """Проверка TOTP с окном ±``window`` шагов (компенсация рассинхрона часов)."""
    if not code or not secret_b32:
        return False
    code = code.strip()
    ts = time.time() if at is None else at
    base = int(ts // period)
    for delta in range(-window, window + 1):
        if hmac.compare_digest(_hotp(secret_b32, base + delta), code):
            return True
    return False


def totp_uri(secret_b32: str, *, account: str, issuer: str = "RuspromSender") -> str:
    """otpauth://-URI для QR-кода привязки в приложении."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30")


# --------------------------------------------------------------------------- #
# Сессии + фасад Auth
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Principal:
    """Аутентифицированный субъект (для проверок доступа в API)."""
    user_id: int
    username: str
    role: str

    @property
    def is_owner(self) -> bool:
        return self.role == ROLE_OWNER


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Auth:
    """Фасад аутентификации поверх store (users/sessions)."""

    def __init__(self, store: Any, *, session_ttl_hours: int = _SESSION_TTL_HOURS):
        self._store = store
        self._ttl = int(session_ttl_hours)

    # ---- пользователи ---- #

    def create_user(self, *, username: str, password: str, role: str = ROLE_MANAGER,
                    email: Optional[str] = None, enable_2fa: bool = False) -> dict:
        if role not in _ROLES:
            raise AuthError(f"unknown role {role!r}")
        if self._store.get_user_by_username(username) is not None:
            raise AuthError(f"user {username!r} already exists")
        totp_secret = generate_totp_secret() if enable_2fa else None
        uid = self._store.create_user(
            username=username, password_hash=hash_password(password),
            role=role, email=email, totp_secret=totp_secret)
        out = {"user_id": uid, "username": username, "role": role}
        if totp_secret:
            out["totp_secret"] = totp_secret
            out["totp_uri"] = totp_uri(totp_secret, account=username)
        return out

    def set_password(self, user_id: int, new_password: str) -> None:
        # Ревью (подтверждено): раньше два отдельных вызова — падение между
        # ними оставляло старые сессии валидными при уже сменённом пароле.
        # Теперь одна транзакция; фолбэк для мок-store без метода.
        new_hash = hash_password(new_password)
        atomic = getattr(self._store, "change_password_and_revoke", None)
        if callable(atomic):
            atomic(user_id, new_hash)
            return
        self._store.update_user(user_id, password_hash=new_hash)
        self._store.revoke_user_sessions(user_id)  # разлогинить старые сессии

    def enable_2fa(self, user_id: int) -> dict:
        secret = generate_totp_secret()
        self._store.update_user(user_id, totp_secret=secret)
        user = self._store.get_user(user_id)
        return {"totp_secret": secret,
                "totp_uri": totp_uri(secret, account=user.username)}

    def disable_2fa(self, user_id: int) -> None:
        self._store.update_user(user_id, totp_secret=None)
        # Ревью (подтверждено): ослабление фактора аутентификации обязано
        # разлогинить существующие сессии — как и смена пароля.
        self._store.revoke_user_sessions(user_id)

    # ---- вход/сессии ---- #

    def login(self, *, username: str, password: str, totp_code: Optional[str] = None,
              user_agent: Optional[str] = None, ip: Optional[str] = None) -> str:
        """Проверить креды (+2FA если включена), выдать opaque session-токен.

        В БД кладётся только sha256 токена. AuthError на любой неуспех —
        без раскрытия, что именно не так (защита от перебора).
        """
        # Ревью (подтверждено): защита от перебора — durable-счётчик по
        # username с экспоненциальным локом (5 подряд → 30с*2^k, до часа).
        # Guard hasattr: мок-store юнитов без throttle-таблицы.
        throttled = hasattr(self._store, "auth_throttle_state")
        if throttled:
            state = self._store.auth_throttle_state(username)
            locked = state.get("locked_until")
            if locked is not None:
                now = datetime.now(timezone.utc)
                if locked.tzinfo is None:
                    locked = locked.replace(tzinfo=timezone.utc)
                if locked > now:
                    raise AuthError("invalid credentials")  # без деталей о локе

        user = self._store.get_user_by_username(username)
        # constant-time: всегда считаем хеш, даже если юзера нет
        stored = user.password_hash if user else hash_password("x")
        ok = verify_password(password, stored)
        if not user or not user.is_active or not ok:
            if throttled:
                self._store.auth_throttle_bump(username, success=False)
            raise AuthError("invalid credentials")
        if user.totp_secret:
            if not verify_totp(user.totp_secret, totp_code or ""):
                if throttled:
                    self._store.auth_throttle_bump(username, success=False)
                raise AuthError("invalid 2fa code")
        if throttled:
            self._store.auth_throttle_bump(username, success=True)
        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=self._ttl)
        self._store.create_session(user_id=user.id, token_hash=_token_hash(token),
                                   expires_at=expires, user_agent=user_agent, ip=ip)
        try:
            self._store.append_audit(action="login", actor_user_id=user.id, ip=ip)
        except Exception:  # noqa: BLE001
            logger.exception("audit login failed")
        return token

    def resolve(self, token: str) -> Optional[Principal]:
        """Токен → Principal, либо None (нет/протух/отозван/юзер неактивен)."""
        if not token:
            return None
        sess = self._store.get_session_by_token(_token_hash(token))
        if sess is None or sess.revoked:
            return None
        if sess.expires_at is not None and sess.expires_at < datetime.now(timezone.utc):
            return None
        user = self._store.get_user(sess.user_id)
        if user is None or not user.is_active:
            return None
        return Principal(user_id=user.id, username=user.username, role=user.role)

    def logout(self, token: str) -> None:
        self._store.revoke_session(_token_hash(token))

    def require_role(self, principal: Optional[Principal], role: str) -> Principal:
        """Гейт доступа: owner проходит везде; иначе роль должна совпасть."""
        if principal is None:
            raise AuthError("not authenticated")
        if principal.role != role and not principal.is_owner:
            raise AuthError(f"role {role!r} required")
        return principal
