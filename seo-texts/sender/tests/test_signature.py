"""Подпись менеджера в теле письма (канон владельца 23.07).

Имя менеджера привязано к ЯЩИКУ (from_name), юр-атрибуция входит в подпись
(без дубля наименования юрлица от render-футера). Выключается конфигом.
"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from email import message_from_bytes  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.sender import RenderedMessage, Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.tests.test_division_gate import _Gates  # noqa: E402

UTC = timezone.utc


@pytest.fixture
def env(tmp_path):
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    yaml = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db"))
    (tmp_path / "c.yaml").write_text(yaml, encoding="utf-8")
    cfg = Config.load(str(tmp_path / "c.yaml"))
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield cfg, s
    s.close()


def _seed(store):
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email="k@z.ru", domain="z.ru", inn="1"))
    store.set_recipient_validation(rid, valid_status="valid",
                                   mx_provider="yandex")
    store.upsert_mailbox_state(MailboxState(
        mailbox_id="box1@rusprom.ru", provider="yandex",
        day_key=datetime.now(UTC).strftime("%Y-%m-%d"),
        sent_today=0, sent_total=0, ramp_day=60, daily_limit=200,
        last_sent_at=None, paused=False, pause_reason=None))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="m1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    return mid


def _body_of(sndr, cfg, store, mid, rendered):
    """Собрать MIME через send (dry_run в песочницу-заглушку) и вернуть тело."""
    sndr._deliver = lambda *a, **k: None
    msg = store.get_message(mid)
    # from_name первого ящика
    mb = cfg.mailboxes()[0]
    captured = {}
    orig = sndr._build_mime

    def spy(headers, rnd, **kw):
        captured["mime"] = orig(headers, rnd, **kw)
        return captured["mime"]
    sndr._build_mime = spy
    sndr.send(msg, rendered, mb.mailbox_id, now=datetime.now(UTC), manual=True)
    parsed = message_from_bytes(captured["mime"])
    for part in parsed.walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode("utf-8"), mb.from_name
    return "", mb.from_name


def test_signature_uses_mailbox_name(env):
    cfg, store = env
    mid = _seed(store)
    sndr = Sender(cfg, store, Suppression(store), _Gates(), dry_run=True)
    body, from_name = _body_of(
        sndr, cfg, store, mid,
        RenderedMessage(subject="Тема", body="Здравствуйте! Предложение.",
                        unfilled_fields=()))
    manager = from_name.split(",")[0].strip()
    assert "С уважением," in body
    assert manager in body                       # имя менеджера из ЯЩИКА
    assert "«Компрессор Центр»" in body
    assert "ООО «Руспром», ИНН 2221239841" in body
    # юр-строка одна (нет дубля наименования)
    assert body.count("ООО «Руспром»") == 1


def test_signature_replaces_render_footer(env):
    cfg, store = env
    mid = _seed(store)
    sndr = Sender(cfg, store, Suppression(store), _Gates(), dry_run=True)
    # тело УЖЕ с авто-футером render'а — не должно задвоиться
    body, _ = _body_of(
        sndr, cfg, store, mid,
        RenderedMessage(subject="Тема",
                        body="Текст.\n\n--\nООО «Руспром», ИНН 2221239841",
                        unfilled_fields=()))
    assert body.count("ООО «Руспром»") == 1
    assert body.rstrip().endswith("ООО «Руспром», ИНН 2221239841")
    assert "С уважением," in body


def test_signature_can_be_disabled(env, tmp_path):
    cfg, store = env
    mid = _seed(store)

    class _Off:
        def __init__(self, base):
            self._b = base
        def get(self, k, d=None):
            if k == "personalization.signature_enabled":
                return False
            return self._b.get(k, d)
        def __getattr__(self, n):
            return getattr(self._b, n)

    sndr = Sender(_Off(cfg), store, Suppression(store), _Gates(), dry_run=True)
    body, _ = _body_of(
        sndr, _Off(cfg), store, mid,
        RenderedMessage(subject="Тема", body="Текст без подписи.",
                        unfilled_fields=()))
    assert "С уважением," not in body
    assert "Менеджер по продажам" not in body
