"""FIX волна 2 — хвосты critical/high из REVIEW-FINDINGS (адверс-проверка 26.07).

Каждый тест писался ПАДАЮЩИМ до фикса и зелёным после:
  W2.1 — In-Reply-To/References из БД (чужой Message-ID входящего письма)
         санируются от CR/LF в build_headers (хвост ревью №0: остальные
         заголовки уже чистились, а этот путь — нет; EmailMessage бросал
         ValueError → письмо навсегда зависало в 'sending');
  W2.2 — _build_mime как последний рубеж чистит CR/LF в ЛЮБОМ значении
         заголовка (защита будущих путей сборки, не только build_headers);
  W2.3 — store.release_message: снятие lease НЕМЕДЛЕННО ('sending' →
         'scheduled'), без инкремента attempt_count, только из 'sending';
  W2.4 — orchestrator: pick_mailbox=None больше не держит письмо в 'sending'
         до recover_stale (15 мин простоя) — lease снимается в том же тике.
"""

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, RenderedMessage,
    SequenceStepIn,
)
from sender.orchestrator import Orchestrator  # noqa: E402
from sender.sender import Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402

UTC = timezone.utc
IN_WINDOW = datetime(2026, 7, 21, 8, 0, tzinfo=UTC)  # вторник 11:00 МСК


# --------------------------------------------------------------------------- #
# Фикстуры (реальный Store + Config из BASE_YAML — как в test_fix_p2)
# --------------------------------------------------------------------------- #
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


@dataclass(frozen=True)
class _Decision:
    tripped: bool = False


class _Gates:
    def check_global(self):
        return _Decision()

    def check_domain(self, domain, campaign_id=None):
        return _Decision()

    def check_mailbox(self, mailbox_id):
        return _Decision()


class _RecordingClient:
    """SMTP-клиент, пишущий последовательность вызовов и последний MIME."""

    def __init__(self, calls):
        self._calls = calls

    def starttls(self):
        self._calls.append("starttls")

    def ehlo(self):
        self._calls.append("ehlo")

    def login(self, *a):
        self._calls.append("login")

    def sendmail(self, frm, to, data):
        self._calls.append("sendmail")
        self.last_mime = data

    def quit(self):
        pass


def _seed_mailbox(store, mailbox_id="box1@rusprom.ru", day=IN_WINDOW):
    store.upsert_mailbox_state(MailboxState(
        mailbox_id=mailbox_id, provider="yandex",
        day_key=day.strftime("%Y-%m-%d"), sent_today=0, sent_total=0,
        ramp_day=30, daily_limit=30, last_sent_at=None,
        paused=False, pause_reason=None))


def _seed_message(store, email="w2@x.ru", key="w2k", in_reply_to=None):
    cid = store.create_campaign(CampaignIn(
        name="W2", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="Т", body_tmpl="Б"))
    rid = store.upsert_recipient(RecipientIn(email=email, domain="x.ru"))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=key, campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=IN_WINDOW - timedelta(hours=1),
        in_reply_to=in_reply_to))
    return cid, sid, rid, mid


# --------------------------------------------------------------------------- #
# W2.1 — CR/LF в in_reply_to из БД не инъецирует заголовки и не роняет отправку
# --------------------------------------------------------------------------- #
def test_w21_in_reply_to_crlf_sanitized(config, store, suppression):
    """Message-ID входящего письма — чужие данные: CR/LF в них раньше уходил
    в EmailMessage сырым → ValueError → письмо навсегда в 'sending'."""
    calls = []
    sndr = Sender(config, store, suppression, _Gates(), dry_run=False)
    client_box = {}

    def opener(host, port, use_ssl):
        c = _RecordingClient(calls)
        client_box["c"] = c
        return c

    sndr._smtp_opener = opener
    os.environ["BOX1_PASSWORD"] = "secret"
    _seed_mailbox(store)
    evil = "<ok@x.ru>\r\nBcc: attacker@evil.com\r\nX-Evil: 1"
    _cid, _sid, _rid, mid = _seed_message(store, in_reply_to=evil)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    assert claimed and claimed[0].in_reply_to == evil  # яд реально в БД

    result = sndr.send(claimed[0], RenderedMessage(subject="Т", body="Б"),
                       "box1@rusprom.ru", now=IN_WINDOW)
    assert result.ok  # не ValueError, письмо не «ядовитое»

    mime = client_box["c"].last_mime
    if isinstance(mime, str):
        mime = mime.encode("utf-8")
    from email import message_from_bytes
    parsed = message_from_bytes(mime)
    # Инъекция не породила настоящих заголовков…
    assert parsed["Bcc"] is None
    assert parsed["X-Evil"] is None
    # …а In-Reply-To/References стали одной логической строкой.
    for name in ("In-Reply-To", "References"):
        value = parsed[name]
        assert value is not None
        assert "attacker@evil.com" in value  # остался текстом внутри значения
    # письмо действительно ушло и помечено sent
    assert store.get_message(mid).status == "sent"


# --------------------------------------------------------------------------- #
# W2.2 — _build_mime чистит CR/LF в любом значении заголовка (последний рубеж)
# --------------------------------------------------------------------------- #
def test_w22_build_mime_sanitizes_any_header(config, store, suppression):
    sndr = Sender(config, store, suppression, _Gates(), dry_run=True)
    headers = {
        "Message-ID": "<w2@x.ru>",
        "To": "w2@x.ru",
        "Subject": "тема",
        # будущий/сторонний путь сборки мог бы принести грязное значение
        "X-Custom": "a\r\nBcc: attacker@evil.com",
    }
    mime = sndr._build_mime(headers, RenderedMessage(subject="тема", body="Б"))
    from email import message_from_bytes
    parsed = message_from_bytes(mime)
    assert parsed["Bcc"] is None
    assert "attacker@evil.com" in parsed["X-Custom"]


# --------------------------------------------------------------------------- #
# W2.3 — store.release_message: немедленное снятие lease
# --------------------------------------------------------------------------- #
def test_w23_release_message_returns_to_scheduled(store):
    _cid, _sid, _rid, mid = _seed_message(store)
    claimed = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    assert claimed and store.get_message(mid).status == "sending"

    assert store.release_message(mid) is True
    msg = store.get_message(mid)
    assert msg.status == "scheduled"
    assert msg.claimed_at is None
    # «некому слать» — не ошибка письма: попытки не накручиваются
    assert msg.attempt_count == 0
    # письмо снова claimable БЕЗ ожидания lease_ttl
    again = store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    assert [m.id for m in again] == [mid]


def test_w23_release_message_only_from_sending(store):
    """sent/failed/pending_review release не трогает (нет тихой реанимации)."""
    _cid, _sid, _rid, mid = _seed_message(store)
    store.claim_due_messages(
        now=IN_WINDOW, mailbox_ids=["box1@rusprom.ru"], limit=1)
    store.mark_sent(mid, "<rfc@x>", IN_WINDOW)

    assert store.release_message(mid) is False
    assert store.get_message(mid).status == "sent"


# --------------------------------------------------------------------------- #
# W2.4 — orchestrator: нет ящика → lease снят в том же тике (не через 15 мин)
# --------------------------------------------------------------------------- #
class _NoMailboxSender:
    """Сендер, у которого прямо сейчас нет доступного ящика."""

    def __init__(self):
        self.dry_run = False

    def pick_mailbox(self, recipient, campaign):
        return None

    def send(self, message, rendered, mailbox_id):  # pragma: no cover
        raise AssertionError("send не должен вызываться без ящика")


class _NoopCadence:
    def plan_campaign(self, campaign_id, *, now):
        return []


class _NoopGates:
    def evaluate_all(self):
        return []


class _NoopImap:
    def poll_once(self, mailbox_id):
        return []


class _NoopWarmup:
    def run_cycle(self, mailbox_id, *, now):
        from sender.dtos import WarmupCycleResult
        return WarmupCycleResult(mailbox_id=mailbox_id, sent=0, target=0,
                                 reputation_score=None)


class _Personalizer:
    def render(self, step, recipient, campaign):
        return RenderedMessage(subject="s", body="b")


class _OrchConfig:
    def __init__(self, boxes):
        self._boxes = boxes

    def get(self, key, default=None):
        return {"orchestrator.active_campaigns": []}.get(key, default)

    def mailboxes(self):
        return self._boxes


def test_w24_no_mailbox_releases_lease_same_tick(store):
    """Ревью №27: раньше письмо оставалось в 'sending' до recover_stale
    (lease_ttl=900с) — гарантированные 15 минут простоя каждому письму,
    которому в момент claim не нашлось ящика."""
    @dataclass
    class _Box:
        mailbox_id: str
        provider: str = "fake"

    _seed_mailbox(store, "mb1")
    cid, _sid, _rid, mid = _seed_message(store)
    orch = Orchestrator(
        _OrchConfig([_Box("mb1")]), store, _NoMailboxSender(), _NoopCadence(),
        _NoopGates(), _NoopImap(), _NoopWarmup(), analytics=None,
        personalizer=_Personalizer())
    orch.active_campaign_ids = [cid]
    store.set_campaign_status(cid, "active")

    result = orch.tick(now=IN_WINDOW)
    assert result.skipped == 1
    msg = store.get_message(mid)
    # lease снят немедленно: письмо снова 'scheduled', а не мёртвое 'sending'
    assert msg.status == "scheduled"
    assert msg.claimed_at is None
