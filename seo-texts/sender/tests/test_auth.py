"""Тесты auth (BUILD-NEW): пароли pbkdf2, TOTP 2FA, сессии, роли."""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.store import Store  # noqa: E402
from sender.auth import (  # noqa: E402
    Auth, AuthError, Principal, hash_password, verify_password,
    generate_totp_secret, totp_now, verify_totp, totp_uri, ROLE_OWNER, ROLE_MANAGER,
)


@pytest.fixture
def auth(tmp_path):
    s = Store(str(tmp_path / "a.db"))
    s.init_schema()
    return Auth(s)


# ---- пароли ----

def test_password_roundtrip():
    h = hash_password("Секрет-123")
    assert h.startswith("pbkdf2$")
    assert verify_password("Секрет-123", h) is True
    assert verify_password("wrong", h) is False


def test_password_unique_salt():
    assert hash_password("x") != hash_password("x")  # соль случайна


def test_verify_bad_format():
    assert verify_password("x", "garbage") is False
    assert verify_password("x", "") is False


def test_empty_password_rejected():
    with pytest.raises(AuthError):
        hash_password("")


# ---- TOTP ----

def test_totp_verify_current():
    sec = generate_totp_secret()
    assert verify_totp(sec, totp_now(sec)) is True
    assert verify_totp(sec, "000000") is False
    assert verify_totp(sec, "") is False


def test_totp_window_tolerates_clock_skew():
    sec = generate_totp_secret()
    now = 1_800_000_000.0
    prev = totp_now(sec, at=now - 30)  # предыдущий шаг
    assert verify_totp(sec, prev, at=now, window=1) is True
    assert verify_totp(sec, prev, at=now, window=0) is False


def test_totp_uri():
    uri = totp_uri("ABC234", account="ivan@x.ru")
    assert uri.startswith("otpauth://totp/") and "secret=ABC234" in uri


# ---- пользователи / вход ----

def test_create_and_login(auth):
    auth.create_user(username="kirill", password="ownerpass", role=ROLE_OWNER)
    tok = auth.login(username="kirill", password="ownerpass")
    p = auth.resolve(tok)
    assert isinstance(p, Principal) and p.username == "kirill" and p.is_owner


def test_duplicate_user_rejected(auth):
    auth.create_user(username="k", password="p")
    with pytest.raises(AuthError):
        auth.create_user(username="k", password="p2")


def test_unknown_role_rejected(auth):
    with pytest.raises(AuthError):
        auth.create_user(username="k", password="p", role="admin")


def test_login_bad_password(auth):
    auth.create_user(username="k", password="right")
    with pytest.raises(AuthError):
        auth.login(username="k", password="wrong")


def test_login_unknown_user(auth):
    with pytest.raises(AuthError):
        auth.login(username="ghost", password="x")


def test_inactive_user_cannot_login(auth):
    r = auth.create_user(username="k", password="p")
    auth._store.update_user(r["user_id"], is_active=False)
    with pytest.raises(AuthError):
        auth.login(username="k", password="p")


# ---- 2FA ----

def test_login_with_2fa(auth):
    r = auth.create_user(username="m", password="p", enable_2fa=True)
    secret = r["totp_secret"]
    with pytest.raises(AuthError):  # без кода
        auth.login(username="m", password="p")
    with pytest.raises(AuthError):  # неверный код
        auth.login(username="m", password="p", totp_code="000000")
    tok = auth.login(username="m", password="p", totp_code=totp_now(secret))
    assert auth.resolve(tok).username == "m"


def test_enable_disable_2fa(auth):
    r = auth.create_user(username="m", password="p")
    info = auth.enable_2fa(r["user_id"])
    assert "totp_secret" in info
    # теперь 2FA требуется
    with pytest.raises(AuthError):
        auth.login(username="m", password="p")
    auth.disable_2fa(r["user_id"])
    assert auth.resolve(auth.login(username="m", password="p")) is not None


# ---- сессии ----

def test_logout_invalidates(auth):
    auth.create_user(username="k", password="p")
    tok = auth.login(username="k", password="p")
    assert auth.resolve(tok) is not None
    auth.logout(tok)
    assert auth.resolve(tok) is None


def test_set_password_revokes_sessions(auth):
    r = auth.create_user(username="k", password="p")
    tok = auth.login(username="k", password="p")
    auth.set_password(r["user_id"], "newpass")
    assert auth.resolve(tok) is None  # старая сессия отозвана
    assert auth.resolve(auth.login(username="k", password="newpass")) is not None


def test_resolve_garbage_token(auth):
    assert auth.resolve("nonexistent") is None
    assert auth.resolve("") is None


# ---- роли ----

def test_require_role(auth):
    auth.create_user(username="owner", password="p", role=ROLE_OWNER)
    auth.create_user(username="mgr", password="p", role=ROLE_MANAGER)
    owner = auth.resolve(auth.login(username="owner", password="p"))
    mgr = auth.resolve(auth.login(username="mgr", password="p"))
    # owner проходит любой гейт
    assert auth.require_role(owner, ROLE_MANAGER).username == "owner"
    assert auth.require_role(owner, ROLE_OWNER).username == "owner"
    # manager проходит manager, но не owner
    assert auth.require_role(mgr, ROLE_MANAGER).username == "mgr"
    with pytest.raises(AuthError):
        auth.require_role(mgr, ROLE_OWNER)
    with pytest.raises(AuthError):
        auth.require_role(None, ROLE_MANAGER)
