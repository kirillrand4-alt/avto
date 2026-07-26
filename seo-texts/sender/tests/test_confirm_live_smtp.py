"""Доказательство «реально уходит по SMTP тут же» на ЖИВОМ SMTP-сервере.

aiosmtpd поднят на localhost — оператор жмёт approve, письмо проходит РЕАЛЬНЫЙ
SMTP-диалог (MAIL FROM / RCPT TO / DATA) и оседает в приёмнике. Наружу ничего
не уходит (127.0.0.1), но путь — настоящий SMTP, не мок. Проверяем и исходящее,
и ответ в тред.
"""

import os
import socket
import sys
import threading
import time as _time

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

pytest.importorskip("aiosmtpd")
from aiosmtpd.controller import Controller  # noqa: E402

from sender.confirm import ConfirmSend  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.reply_pipeline import ReplyPipeline  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.tests.test_reply_pipeline import (  # noqa: E402
    _Gates, _caller_send, _signal, _ev,
)
from datetime import datetime, timezone

UTC = timezone.utc


class _Collector:
    def __init__(self):
        self.messages = []
        self._lock = threading.Lock()

    async def handle_DATA(self, server, session, envelope):
        with self._lock:
            self.messages.append(
                (envelope.mail_from, list(envelope.rcpt_tos), envelope.content))
        return "250 OK"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def smtp():
    handler = _Collector()
    port = _free_port()
    ctl = Controller(handler, hostname="127.0.0.1", port=port)
    ctl.start()
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            _time.sleep(0.05)
    yield handler, port
    ctl.stop()


@pytest.fixture
def config(tmp_path, smtp):
    _handler, port = smtp
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    yaml = (BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db"))
            .replace('sandbox_smtp: "localhost:8025"',
                     f'sandbox_smtp: "127.0.0.1:{port}"'))
    path = tmp_path / "c.yaml"
    path.write_text(yaml, encoding="utf-8")
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


def _sandbox_sender(config, store, supp):
    # dry_run=True → реальный SMTP-диалог, но в локальную песочницу (127.0.0.1)
    return Sender(config, store, supp, _Gates(), dry_run=True)


def _seed_outbound(store):
    cid = store.create_campaign(CampaignIn(
        name="Ручная", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0, subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email="klient@zavod.ru", domain="zavod.ru", inn="4201000625"))
    store.set_recipient_validation(rid, valid_status="valid", mx_provider="yandex")
    for mb in ("box1@rusprom.ru", "box2@rusprom.ru", "box3@rusprom.ru",
               "box4@rusprom.ru", "box5@rusprom.ru"):
        prov = "yandex" if mb in ("box1@rusprom.ru", "box2@rusprom.ru") else "mailru"
        store.upsert_mailbox_state(MailboxState(
            mailbox_id=mb, provider=prov,
            day_key=datetime.now(UTC).strftime("%Y-%m-%d"),
            sent_today=0, sent_total=0, ramp_day=60, daily_limit=200,
            last_sent_at=None, paused=False, pause_reason=None))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="m1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)),
        status="pending_review")
    return cid, rid, mid


def test_manual_approve_delivers_over_real_smtp(config, store, smtp):
    """Оператор одобрил → письмо реально прошло SMTP и лежит в приёмнике."""
    handler, _port = smtp
    supp = Suppression(store)
    sndr = _sandbox_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed_outbound(store)
    r = cs.submit(email="klient@zavod.ru", inn="4201000625", campaign_id=cid,
                  recipient_id=rid, message_id=mid,
                  subject="Компрессор под ваш проект",
                  body="Здравствуйте! Предложение.\n--\nООО «Руспром», ИНН 2221239841")

    assert cs.approve(r.review_id, operator="kirill") is True

    # РЕАЛЬНЫЙ SMTP-сервер принял письмо
    assert len(handler.messages) == 1
    mail_from, rcpt_tos, content = handler.messages[0]
    assert "klient@zavod.ru" in rcpt_tos
    from email import message_from_bytes
    from email.header import decode_header, make_header
    parsed = message_from_bytes(content)
    subj = str(make_header(decode_header(parsed["Subject"])))
    assert subj == "Компрессор под ваш проект"
    assert "List-Unsubscribe" in parsed  # юр-гейт: отписка в заголовке
    assert store.get_message(mid).status == "sent"
    assert store.confirm_get(r.review_id)["status"] == "sent"


def test_manual_reply_delivers_over_real_smtp(config, store, smtp):
    """Ответ клиенту реально уходит в тред через живой SMTP."""
    handler, _port = smtp
    supp = Suppression(store)
    sndr = _sandbox_sender(config, store, supp)
    # ящик для ответа
    store.upsert_mailbox_state(MailboxState(
        mailbox_id="box1@rusprom.ru", provider="yandex",
        day_key=datetime.now(UTC).strftime("%Y-%m-%d"),
        sent_today=0, sent_total=0, ramp_day=60, daily_limit=200,
        last_sent_at=None, paused=False, pause_reason=None))
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    pipe = ReplyPipeline(config, store, cs, caller=_caller_send)
    rid = store.upsert_recipient(RecipientIn(
        email="lead@zavod.ru", domain="zavod.ru", inn="4201000625",
        company_name="ООО Завод", contact_name="Пётр Иванов"))
    rcp = store.get_recipient(rid)

    review_id = pipe.draft_for_incoming(rcp, _signal("interested"), _ev())
    assert cs.approve(review_id, operator="kirill") is True

    assert len(handler.messages) == 1
    _mf, rcpt_tos, content = handler.messages[0]
    assert "lead@zavod.ru" in rcpt_tos
    from email import message_from_bytes
    parsed = message_from_bytes(content)
    assert parsed["In-Reply-To"] == "<in-123@zavod.ru>"  # в треде
    body = parsed.get_payload(decode=True).decode("utf-8")
    assert "ООО «Руспром»" in body


def test_edited_recipient_email_reaches_smtp(config, store, smtp):
    """Ревью №40 (критично): оператор сменил адрес в карточке — письмо ДОЛЖНО
    уйти на новый адрес, а не на исходный из recipients."""
    handler, _port = smtp
    supp = Suppression(store)
    sndr = _sandbox_sender(config, store, supp)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     sender=sndr)
    cid, rid, mid = _seed_outbound(store)
    # в панели у компании два контакта: приёмная (исходный) и директор
    panel = {"emails": [
        {"email": "klient@zavod.ru", "role": "приёмная", "mx_ok": True},
        {"email": "director@zavod.ru", "role": "директор", "mx_ok": True}]}
    r = cs.submit(email="klient@zavod.ru", inn="4201000625", campaign_id=cid,
                  recipient_id=rid, message_id=mid,
                  subject="Компрессор под ваш проект",
                  body="Здравствуйте! Предложение.\n--\nООО «Руспром», ИНН 2221239841",
                  panel=panel)
    # оператор выбирает именной адрес
    cs.set_recipient_email(r.review_id, "director@zavod.ru", operator="kirill")
    assert cs.approve(r.review_id, operator="kirill") is True

    assert len(handler.messages) == 1
    _mail_from, rcpt_tos, content = handler.messages[0]
    # конверт-to = новый адрес, старого в получателях НЕТ
    assert "director@zavod.ru" in rcpt_tos
    assert "klient@zavod.ru" not in rcpt_tos
    from email import message_from_bytes
    parsed = message_from_bytes(content)
    assert "director@zavod.ru" in parsed["To"]


def test_reply_lands_in_thread(config, store, smtp):
    """Правка владельца 26.07: ответ клиенту должен прийти ВЕТКОЙ его переписки,
    а не отдельным письмом. Проверяем: In-Reply-To = Message-ID входящего,
    References = вся цепочка, тема с «Re:»."""
    handler, _port = smtp
    supp = Suppression(store)
    sndr = _sandbox_sender(config, store, supp)
    orig_id = "<orig-123@zavod.ru>"
    chain = "<first-1@rusprom.ru> <second-2@zavod.ru>"
    sndr.send_reply(
        to_email="klient@zavod.ru", subject="Компрессоры",
        body="Отвечаем по вашему вопросу.\n--\nООО «Руспром»",
        mailbox_id="box1@rusprom.ru", in_reply_to=orig_id,
        references=chain)

    assert len(handler.messages) == 1
    _mf, _rcpt, content = handler.messages[0]
    from email import message_from_bytes
    from email.header import decode_header, make_header
    parsed = message_from_bytes(content)
    assert parsed["In-Reply-To"] == orig_id
    refs = (parsed["References"] or "").split()
    # вся цепочка + Message-ID входящего, без дублей и в порядке
    assert refs == ["<first-1@rusprom.ru>", "<second-2@zavod.ru>", orig_id]
    subj = str(make_header(decode_header(parsed["Subject"])))
    assert subj.startswith("Re: ")


def test_reply_does_not_double_re_prefix(config, store, smtp):
    """Если оператор уже написал «Re:» — второй раз не добавляем."""
    handler, _port = smtp
    supp = Suppression(store)
    sndr = _sandbox_sender(config, store, supp)
    sndr.send_reply(to_email="klient@zavod.ru", subject="Re: Компрессоры",
                    body="Текст.\n--\nООО «Руспром»",
                    mailbox_id="box1@rusprom.ru",
                    in_reply_to="<x-1@zavod.ru>")
    from email import message_from_bytes
    from email.header import decode_header, make_header
    parsed = message_from_bytes(handler.messages[0][2])
    subj = str(make_header(decode_header(parsed["Subject"])))
    assert subj == "Re: Компрессоры"
