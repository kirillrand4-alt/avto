"""Ручная immediate-send исходящих: оператор нажал «Отправить» → реальный SMTP.

⛔ Наружу НЕ ходим: SMTP-opener замокан, но путь БОЕВОЙ (dry_run=False):
login+sendmail реально вызываются — доказательство, что письмо ушло бы в сеть.
Проверяем: ручной approve/edit шлёт немедленно; окно/пейсинг обходятся;
suppression/лимит/пауза — остаются; без live-режима approve только в очередь.
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.confirm import ConfirmBlockedError, ConfirmSend  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.errors import SuppressedError  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402

UTC = timezone.utc
# Воскресенье 03:00 UTC — ЗАВЕДОМО вне окна отправки (09:30-17:30 МСК Пн-Пт).
OUT_OF_WINDOW = datetime(2026, 7, 19, 3, 0, tzinfo=UTC)


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

    def evaluate_all(self):
        return []


class _LiveOpener:
    """Мок SMTP-клиента боевого пути: фиксирует login+sendmail, наружу не ходит."""

    def __init__(self):
        self.calls = []
        self.sent = []

    def __call__(self, host, port, use_ssl):
        opener = self
        opener.calls.append(("open", host, port, use_ssl))

        class _Client:
            def starttls(self):
                opener.calls.append(("starttls",))

            def ehlo(self):
                pass

            def login(self, login, pwd):
                opener.calls.append(("login", login))

            def sendmail(self, frm, to, data):
                opener.sent.append((frm, to, data))

            def quit(self):
                pass

        return _Client()


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


def _live_sender(config, store, suppression):
    """Боевой sender (dry_run=False) с мок-opener."""
    sndr = Sender(config, store, suppression, _Gates(), dry_run=False)
    opener = _LiveOpener()
    sndr._smtp_opener = opener
    return sndr, opener


def _seed(store, email="lead@zavod.ru", inn="4201000625"):
    cid = store.create_campaign(CampaignIn(
        name="Ручная", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email=email, domain=email.split("@")[1], inn=inn))
    # провайдер получателя (для route_pool) ставим через валидацию
    store.set_recipient_validation(rid, valid_status="valid", mx_provider="yandex")
    # все боевые ящики BASE_YAML — с запасом дневного лимита
    for mb in ("box1@rusprom.ru", "box2@rusprom.ru", "box3@rusprom.ru",
               "box4@rusprom.ru", "box5@rusprom.ru"):
        prov = "yandex" if mb in ("box1@rusprom.ru", "box2@rusprom.ru") else "mailru"
        store.upsert_mailbox_state(MailboxState(
            mailbox_id=mb, provider=prov,
            day_key=datetime.now(UTC).strftime("%Y-%m-%d"),
            sent_today=0, sent_total=0, ramp_day=60, daily_limit=200,
            last_sent_at=None, paused=False, pause_reason=None))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=f"m:{email}", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)),
        status="pending_review")
    return cid, rid, mid


def _submit(cs, store, cid, rid, mid, email="lead@zavod.ru", inn="4201000625"):
    r = cs.submit(email=email, inn=inn, campaign_id=cid, recipient_id=rid,
                  message_id=mid, subject="Тема письма",
                  body="Здравствуйте! Предложение. --\nООО «Руспром», ИНН 2221239841")
    return r.review_id


class _Cfg:
    def __init__(self, base, **over):
        self._base = base
        self._over = over

    def get(self, key, default=None):
        if key in self._over:
            return self._over[key]
        return self._base.get(key, default)

    def __getattr__(self, name):
        return getattr(self._base, name)


# --------------------------------------------------------------------------- #
# Ручной approve в live-режиме → реальный SMTP немедленно
# --------------------------------------------------------------------------- #
def test_manual_approve_sends_live_immediately(config, store):
    supp = Suppression(store)
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    assert cs.live is True
    cid, rid, mid = _seed(store)
    review_id = _submit(cs, store, cid, rid, mid)

    assert cs.approve(review_id, operator="kirill") is True

    # реальный боевой SMTP-путь пройден: login + sendmail вызваны
    assert len(opener.sent) == 1
    assert any(c[0] == "login" for c in opener.calls)
    # письмо и review помечены отправленными
    assert store.get_message(mid).status == "sent"
    assert store.confirm_get(review_id)["status"] == "sent"
    # send_log зафиксировал контакт
    assert store.last_contact(email="lead@zavod.ru") is not None


def test_manual_send_bypasses_window(config, store):
    """Вне окна отправки ручная кнопка всё равно шлёт (окно — про автоматику)."""
    supp = Suppression(store)
    sndr, opener = _live_sender(config, store, supp)
    # окно точно закрыто СЕЙЧАС? не полагаемся — проверяем прямой manual-путь
    cid, rid, mid = _seed(store)
    from sender.dtos import RenderedMessage
    msg = store.get_message(mid)
    # manual=True: окно не проверяется даже в заведомо нерабочее время
    res = sndr.send(msg, RenderedMessage(subject="s", body="b"),
                    "box1@rusprom.ru", now=OUT_OF_WINDOW, manual=True)
    assert res.ok and len(opener.sent) == 1
    # а без manual — то же письмо (свежий) вне окна отклоняется
    _cid2, _rid2, mid2 = _seed(store, email="two@zavod.ru", inn="5050029646")
    from sender.errors import RateLimitExceeded
    with pytest.raises(RateLimitExceeded):
        sndr.send(store.get_message(mid2),
                  RenderedMessage(subject="s", body="b"),
                  "box1@rusprom.ru", now=OUT_OF_WINDOW, manual=False)


def test_manual_send_still_honors_suppression(config, store):
    """Юр-заслон сильнее ручной кнопки: отписанному не уходит даже вручную."""
    supp = Suppression(store)
    supp.add_email("lead@zavod.ru", "unsubscribe")
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed(store)
    # submit авто-скипнет (заслон очереди) — создадим review в обход, как pending
    rid_review, _ = store.confirm_submit(
        email="lead@zavod.ru", inn="4201000625", campaign_id=cid,
        recipient_id=rid, message_id=mid, subject="s", body="b",
        status="pending")
    with pytest.raises(ConfirmBlockedError):
        cs.approve(rid_review, operator="op")
    assert opener.sent == []  # SMTP не тронут
    assert store.get_message(mid).status == "pending_review"


def test_manual_send_blocked_when_mailbox_paused(config, store):
    supp = Suppression(store)
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed(store)
    # все ящики на паузе → слать неоткуда даже вручную
    for mb in store.iter_mailbox_states():
        store.set_mailbox_paused(mb.mailbox_id, True, "gate")
    review_id = _submit(cs, store, cid, rid, mid)
    with pytest.raises(ConfirmBlockedError):
        cs.approve(review_id, operator="op")
    assert opener.sent == []


# --------------------------------------------------------------------------- #
# edit в live-режиме → правленый текст уходит + золотая пара
# --------------------------------------------------------------------------- #
def test_manual_edit_sends_edited_and_keeps_diff(config, store):
    supp = Suppression(store)
    sndr, opener = _live_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed(store)
    review_id = _submit(cs, store, cid, rid, mid)

    assert cs.edit(review_id, body="Правленый текст.\n--\nООО «Руспром», ИНН 2221239841",
                   operator="kirill") is True
    assert len(opener.sent) == 1
    # правленое тело реально ушло в MIME
    mime = opener.sent[0][2]
    if isinstance(mime, bytes):
        mime = mime.decode("utf-8", "replace")
    assert "Правленый текст" in mime
    row = store.confirm_get(review_id)
    assert row["status"] == "sent"
    assert row["diff_text"] and "+Правленый текст." in row["diff_text"]
    # золотая пара доступна для калибровки ДАЖЕ после live-отправки (status='sent'):
    # выборка по факту правки (edited_body), не по статусу — иначе боевые пары терялись
    pairs = cs.golden_pairs()
    assert len(pairs) == 1
    assert pairs[0]["review_id"] == review_id
    assert pairs[0]["original_body"] and pairs[0]["edited_body"]
    assert "Правленый текст" in pairs[0]["edited_body"]
    assert pairs[0]["original_body"] != pairs[0]["edited_body"]


# --------------------------------------------------------------------------- #
# Без live-режима (sender=None) — approve только в очередь
# --------------------------------------------------------------------------- #
def test_queue_mode_when_live_off(config, store):
    supp = Suppression(store)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=None)
    assert cs.live is False
    cid, rid, mid = _seed(store)
    review_id = _submit(cs, store, cid, rid, mid)
    assert cs.approve(review_id, operator="op") is True
    # письмо в очередь на оркестратор (scheduled), НЕ отправлено
    assert store.get_message(mid).status == "scheduled"
    assert store.confirm_get(review_id)["status"] == "approved"
    assert store.last_contact(email="lead@zavod.ru") is None  # send_log пуст


# --------------------------------------------------------------------------- #
# wiring: confirm.live_send флаг собирает боевой sender
# --------------------------------------------------------------------------- #
def test_wiring_live_send_flag(config, store):
    from sender.wiring import build_deps
    deps_off = build_deps(_Cfg(config, **{"confirm.live_send": False}), store,
                          dry_run=True)
    assert deps_off.confirm.live is False

    deps_on = build_deps(_Cfg(config, **{"confirm.live_send": True}), store,
                         dry_run=True)
    assert deps_on.confirm.live is True
    # live-sender боевой (не dry_run), даже что панель dry_run=True
    assert deps_on.confirm._sender.dry_run is False
