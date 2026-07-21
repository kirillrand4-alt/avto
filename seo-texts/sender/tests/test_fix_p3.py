"""FIX П3 (medium) — тесты дефектов из REVIEW-FINDINGS.

Каждый тест писался ПАДАЮЩИМ до фикса и зелёным после:
  П3.1 — XSS: токен на GET-странице отписки экранируется;
  П3.2 — Content-Length: мусор -> 400, огромный -> 413 (без чтения тела);
  П3.3 — RCPT-проба: нечисловой код ответа не роняет батч валидации;
  П3.4 — extra_json не перетирается пустым extra при повторном импорте;
  П3.5 — plan() автоответчика: suppressed-адресату reply_* не планируются;
  П3.6 — inject_pixel экранирует URL пикселя в атрибуте src.
"""

import os
import socket
import sys
import threading
import time as _time
from urllib.request import urlopen

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.config import Config  # noqa: E402
from sender.dtos import RecipientIn  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.unsub_server import make_server  # noqa: E402


@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ.setdefault(f"BOX{i}_PASSWORD", "x")
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    path = tmp_path / "config.yaml"
    path.write_text(BASE_YAML.replace("db.db", str(tmp_path / "t.db")),
                    encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def suppression(store):
    return Suppression(store)


@pytest.fixture
def server(config, store, suppression):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = make_server(config, store, suppression, host="127.0.0.1", port=port)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    for _ in range(50):
        try:
            urlopen(f"http://127.0.0.1:{port}/health", timeout=0.1)
            break
        except Exception:
            _time.sleep(0.01)
    yield port
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=1)


def _raw_http(port: int, request: bytes) -> str:
    """Сырой HTTP-запрос (нужен для мусорного/огромного Content-Length)."""
    with socket.create_connection(("127.0.0.1", port), timeout=2) as sock:
        sock.sendall(request)
        sock.settimeout(2)
        chunks = []
        try:
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                chunks.append(data)
        except socket.timeout:
            pass
    return b"".join(chunks).decode("utf-8", "replace")


# --------------------------------------------------------------------------- #
# П3.1 — XSS на GET-странице отписки
# --------------------------------------------------------------------------- #
def test_p31_get_page_escapes_token(server):
    evil = '"><script>alert(1)</script>'
    from urllib.parse import quote
    resp = urlopen(
        f"http://127.0.0.1:{server}/u?t={quote(evil)}", timeout=2)
    body = resp.read().decode("utf-8")
    assert "<script>alert(1)</script>" not in body  # сырым не отражается
    assert "&lt;script&gt;" in body or "%3Cscript%3E" in body


# --------------------------------------------------------------------------- #
# П3.2 — Content-Length: мусор и гигантские значения
# --------------------------------------------------------------------------- #
def test_p32_garbage_content_length_is_400(server):
    req = (
        b"POST /u?t=abc.def HTTP/1.1\r\n"
        b"Host: 127.0.0.1\r\n"
        b"Content-Length: not-a-number\r\n"
        b"Connection: close\r\n\r\n"
    )
    status = _raw_http(server, req).splitlines()[0]
    assert " 400 " in status  # раньше: необработанный ValueError -> 500


def test_p32_huge_content_length_is_413(server):
    req = (
        b"POST /u?t=abc.def HTTP/1.1\r\n"
        b"Host: 127.0.0.1\r\n"
        b"Content-Length: 10485760\r\n"  # 10 МиБ заявлено, тело не шлём
        b"Connection: close\r\n\r\n"
    )
    status = _raw_http(server, req).splitlines()[0]
    assert " 413 " in status  # раньше: блокирующий read(10 МиБ)


# --------------------------------------------------------------------------- #
# П3.3 — RCPT-проба: нечисловой код не роняет батч
# --------------------------------------------------------------------------- #
def test_p33_rcpt_non_int_code_returns_unknown(monkeypatch):
    from sender import validation as vmod

    class _FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ehlo_or_helo_if_needed(self):
            pass

        def mail(self, addr):
            pass

        def rcpt(self, addr):
            return None, b"weird server"  # нестандартный ответ

    monkeypatch.setattr(vmod.smtplib, "SMTP", _FakeSMTP)
    v = vmod.Validation.__new__(vmod.Validation)
    v._smtp_timeout = 1
    v._probe_from = "probe@rusprom.ru"
    # Раньше: TypeError ('<=' not supported...) валил весь батч валидации.
    assert v._smtp_accepts("mx.example.com", "a@b.ru") is None


# --------------------------------------------------------------------------- #
# П3.4 — extra_json не перетирается пустым extra
# --------------------------------------------------------------------------- #
def test_p34_reimport_with_empty_extra_preserves_metadata(store):
    rid = store.upsert_recipient(RecipientIn(
        email="meta@x.ru", domain="x.ru",
        extra={"crm_id": "123", "tag": "a"}))
    # Повторный импорт из CSV: extra по умолчанию пуст.
    rid2 = store.upsert_recipient(RecipientIn(email="meta@x.ru", domain="x.ru"))
    assert rid == rid2
    r = store.get_recipient(rid)
    assert r.extra == {"crm_id": "123", "tag": "a"}  # раньше: {}


def test_p34_nonempty_extra_still_replaces(store):
    rid = store.upsert_recipient(RecipientIn(
        email="meta2@x.ru", domain="x.ru", extra={"old": 1}))
    store.upsert_recipient(RecipientIn(
        email="meta2@x.ru", domain="x.ru", extra={"new": 2}))
    assert store.get_recipient(rid).extra == {"new": 2}


# --------------------------------------------------------------------------- #
# П3.5 — plan() не планирует reply_* подавленному адресату
# --------------------------------------------------------------------------- #
def test_p35_plan_suppressed_no_reply_actions():
    from types import SimpleNamespace
    from sender.autoresponder import AUTO, plan

    sig = SimpleNamespace(kind="hot", phone="+79990000000", language="ru",
                          from_addr="unsubbed@x.ru", subject="Счёт",
                          snippet="давайте счёт")
    actions = plan(sig, mode=AUTO, suppressed=True)
    kinds = [a.kind for a in actions]
    assert "reply_auto" not in kinds
    assert "reply_draft" not in kinds
    # Не-письменные действия сохранены: лид горячий, человек должен увидеть.
    assert "bitrix_push" in kinds
    assert "notify" in kinds
    # Понижение зафиксировано явным флагом для конвейера/оператора.
    flagged = [a for a in actions if a.kind == "flag_contact"]
    assert flagged and flagged[0].payload.get("reason") == "suppressed"


def test_p35_plan_default_keeps_reply(monkeypatch):
    from types import SimpleNamespace
    from sender.autoresponder import AUTO, plan

    sig = SimpleNamespace(kind="hot", phone=None, language="ru",
                          from_addr="live@x.ru", subject="s", snippet="t")
    kinds = [a.kind for a in plan(sig, mode=AUTO)]
    assert "reply_auto" in kinds  # без флага поведение прежнее


# --------------------------------------------------------------------------- #
# П3.6 — inject_pixel экранирует URL в атрибуте
# --------------------------------------------------------------------------- #
def test_p36_inject_pixel_escapes_url():
    from sender.tracking import inject_pixel
    evil = 'https://t.example/o/x" onerror="alert(1)'
    out = inject_pixel("<html><body>hi</body></html>", evil)
    assert 'onerror="alert(1)' not in out
    assert "&quot;" in out
