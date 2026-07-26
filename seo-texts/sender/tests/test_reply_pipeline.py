"""Ручная отправка ОТВЕТОВ: входящее → черновик в очередь → оператор шлёт.

Автоответчик готовит черновик (plan pilot + render_reply + review_chain с
мок-caller), кладёт в confirm-очередь kind='reply'. Оператор в live-режиме
жмёт «Отправить» → sender.send_reply → реальный SMTP (мок-opener видит).
"""

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.confirm import ConfirmSend  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import RecipientIn  # noqa: E402
from sender.reply_pipeline import ReplyPipeline  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402


def _caller_send(prompt: str) -> str:
    """Мок LLM: линзам PASS, судье SEND (единый JSON со всеми полями)."""
    return ('{"verdict":"PASS","problems":[],"fixes":[],'
            '"decision":"SEND","reason":"ок","score":5}')


@dataclass(frozen=True)
class _D:
    tripped: bool = False


class _Gates:
    def check_global(self):
        return _D()

    def check_domain(self, d, c=None):
        return _D()

    def check_mailbox(self, m):
        return _D()


class _LiveOpener:
    def __init__(self):
        self.sent = []

    def __call__(self, host, port, use_ssl):
        opener = self

        class _C:
            def starttls(self): ...
            def ehlo(self): ...
            def login(self, *a): ...

            def sendmail(self, frm, to, data):
                opener.sent.append((frm, to, data))

            def quit(self): ...

        return _C()


@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    path = tmp_path / "c.yaml"
    path.write_text(BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db")),
                    encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


class _Cfg:
    def __init__(self, base, **over):
        self._base, self._over = base, over

    def get(self, key, default=None):
        return self._over.get(key, self._base.get(key, default))

    def __getattr__(self, name):
        return getattr(self._base, name)


def _recipient(store, email="lead@zavod.ru", inn="4201000625"):
    rid = store.upsert_recipient(RecipientIn(
        email=email, domain=email.split("@")[1], inn=inn,
        company_name="ООО Завод", contact_name="Пётр Иванов"))
    return store.get_recipient(rid)


def _signal(kind="interested"):
    return SimpleNamespace(kind=kind, phone=None, redirect_hint=None,
                           deferred_hint=None, contact_hint=None)


def _ev(snippet="Здравствуйте, интересует компрессор, пришлите КП"):
    return SimpleNamespace(snippet=snippet, rfc_message_id="<in-123@zavod.ru>",
                           thread_id="thread-1", from_addr="lead@zavod.ru")


# --------------------------------------------------------------------------- #
# Черновик ответа кладётся в очередь
# --------------------------------------------------------------------------- #
def test_draft_reply_goes_to_queue(config, store):
    supp = Suppression(store)
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    rcp = _recipient(store)

    rid = pipe.draft_for_incoming(rcp, _signal("interested"), _ev())
    assert rid is not None

    row = store.confirm_get(rid)
    assert row["kind"] == "reply"
    assert row["status"] == "pending"
    assert row["email"] == "lead@zavod.ru"
    assert row["in_reply_to"] == "<in-123@zavod.ru>"
    assert row["thread_id"] == "thread-1"
    # #65: атрибуцию дописывает подпись отправки; тело кончается «С уважением,»
    assert row["body"].rstrip().endswith("С уважением,")
    assert row["panel"]["review"]["decision"] == "SEND"


def test_non_respondable_kind_no_draft(config, store):
    supp = Suppression(store)
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    rcp = _recipient(store)
    # unsub_request не в RESPONDABLE — черновик не готовим
    assert pipe.draft_for_incoming(rcp, _signal("unsub_request"), _ev()) is None
    assert store.confirm_counts() == {}


def test_reply_dedup_by_thread(config, store):
    supp = Suppression(store)
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    rcp = _recipient(store)
    r1 = pipe.draft_for_incoming(rcp, _signal(), _ev())
    r2 = pipe.draft_for_incoming(rcp, _signal(), _ev())  # тот же тред
    assert r1 == r2
    assert store.confirm_counts().get("pending") == 1


def test_suppressed_reply_autoskips(config, store):
    supp = Suppression(store)
    supp.add_email("lead@zavod.ru", "unsubscribe")
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    rcp = _recipient(store)
    rid = pipe.draft_for_incoming(rcp, _signal("interested"), _ev())
    # suppressed=True → plan вычёркивает reply_* → None (черновик не готовим)
    assert rid is None


# --------------------------------------------------------------------------- #
# Оператор жмёт «Отправить» → реальный SMTP-ответ в тред
# --------------------------------------------------------------------------- #
def test_manual_approve_reply_sends_live(config, store):
    supp = Suppression(store)
    sndr = Sender(config, store, supp, _Gates(), dry_run=False)
    opener = _LiveOpener()
    sndr._smtp_opener = opener
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                          sender=sndr)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    rcp = _recipient(store)
    rid = pipe.draft_for_incoming(rcp, _signal("interested"), _ev())

    assert confirm.approve(rid, operator="kirill") is True
    # реальный SMTP: ответ ушёл
    assert len(opener.sent) == 1
    from email import message_from_bytes
    raw = opener.sent[0][2]
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    parsed = message_from_bytes(raw)
    assert parsed["In-Reply-To"] == "<in-123@zavod.ru>"  # ответ в треде
    payload = parsed.get_payload(decode=True).decode("utf-8")
    assert "ООО «Руспром»" in payload
    assert store.confirm_get(rid)["status"] == "sent"
    # send_log зафиксировал ответ
    hist = store.send_log_history(email="lead@zavod.ru")
    assert any(h["outcome"] == "reply_sent" for h in hist)


def test_reply_not_sent_when_recipient_unsubscribes_before_approve(config, store):
    """Отписался между входящим и approve → ответ не уходит."""
    supp = Suppression(store)
    sndr = Sender(config, store, supp, _Gates(), dry_run=False)
    opener = _LiveOpener()
    sndr._smtp_opener = opener
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                          sender=sndr)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    rcp = _recipient(store)
    rid = pipe.draft_for_incoming(rcp, _signal("interested"), _ev())
    # теперь отписался
    supp.add_email("lead@zavod.ru", "unsubscribe")
    from sender.errors import SuppressedError
    from sender.confirm import ConfirmBlockedError
    with pytest.raises((SuppressedError, ConfirmBlockedError)):
        confirm.approve(rid, operator="op")
    assert opener.sent == []


# --------------------------------------------------------------------------- #
# Интеграция через imap_watcher: входящий → черновик
# --------------------------------------------------------------------------- #
def test_imap_watcher_wires_reply_draft(config, store):
    from sender.imap_watcher import ImapWatcher
    supp = Suppression(store)
    confirm = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp)
    pipe = ReplyPipeline(config, store, confirm, caller=_caller_send)
    watcher = ImapWatcher(config, store, supp, reply_desk=None,
                          reply_pipeline=pipe)
    rcp = _recipient(store)
    ev = _ev()
    # прямой вызов внутреннего обработчика ответа (минуя IMAP-сеть)
    watcher._handle_reply(rcp.id, None, ev, signal=_signal("interested"))
    rows = confirm.pending()
    assert len(rows) == 1 and rows[0]["kind"] == "reply"
