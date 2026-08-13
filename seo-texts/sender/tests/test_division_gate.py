"""Гейт направлений КЦ/Meyer (§4 ENGINEER-TASKS-BASE-MERGE) — три точки.

Негативные пары из ТЗ (все должны отбиваться, лог фиксирует причину):
  КЦ-ящик × Meyer-компания; ящик без division; компания без division.
Точки: 1) сборка очереди (оркестратор), 2) экран подтверждения (стоп-флаг +
approve заблокирован), 3) диспетчер SMTP (отказ + событие division_gate_block).
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.company_card import (  # noqa: E402
    CompanyCards, build_obzvon_index, division_from_segment,
)
from sender.confirm import ConfirmBlockedError, ConfirmSend  # noqa: E402
from sender.config import Config, ConfigError  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.errors import SuppressedError  # noqa: E402
from sender.sender import RenderedMessage, Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.tests.test_company_card import _HEADER, _KC_ROW, _MEYER_ROW  # noqa: E402

UTC = timezone.utc
KC_INN = "4201000625"      # Компрессор Центр (фикстура)
MEYER_INN = "5404000000"   # Meyer (фикстура)


class _Gates:
    def check_global(self):
        return type("D", (), {"tripped": False})()
    check_domain = lambda self, *a, **k: type("D", (), {"tripped": False})()  # noqa: E731
    check_mailbox = lambda self, *a, **k: type("D", (), {"tripped": False})()  # noqa: E731


class _Cfg:
    def __init__(self, base, **over):
        self._base, self._over = base, over

    def get(self, key, default=None):
        return self._over.get(key, self._base.get(key, default))

    def __getattr__(self, name):
        return getattr(self._base, name)


@pytest.fixture
def cards(tmp_path):
    db = str(tmp_path / "obzvon.db")
    build_obzvon_index(iter([_HEADER, _KC_ROW, _MEYER_ROW]), db)
    return CompanyCards(index_path=db)


@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    # box1/box2 (yandex-пул) — направление КЦ; box3 (mailru) — без division
    yaml = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db"))
    yaml = yaml.replace(
        'password_env: BOX1_PASSWORD',
        'password_env: BOX1_PASSWORD\n    division: kc')
    yaml = yaml.replace(
        'password_env: BOX2_PASSWORD',
        'password_env: BOX2_PASSWORD\n    division: kc')
    path = tmp_path / "c.yaml"
    path.write_text(yaml, encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


def _seed(store, *, inn, mx="yandex"):
    cid = store.create_campaign(CampaignIn(
        name="КЦ база", legal_entity="ООО «Руспром»", legal_inn="7700000000",
        config={"segment": "КЦ"}))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email="klient@zavod.ru", domain="zavod.ru", inn=inn, segment="КЦ"))
    store.set_recipient_validation(rid, valid_status="valid", mx_provider=mx)
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
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    return cid, rid, mid


def _sender(config, store, cards):
    return Sender(config, store, Suppression(store), _Gates(),
                  dry_run=True, cards=cards)


def _rendered():
    return RenderedMessage(subject="Тема", body="Текст", unfilled_fields=())


# -- конфиг -------------------------------------------------------------------


def test_config_division_validated(tmp_path, config):
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    boxes = {m.mailbox_id: m.division for m in config.mailboxes()}
    assert boxes["box1@rusprom.ru"] == "kc"
    assert boxes["box3@rusprom.ru"] is None
    bad = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "b.db")).replace(
        'password_env: BOX1_PASSWORD',
        'password_env: BOX1_PASSWORD\n    division: prodazhi')
    p = tmp_path / "bad.yaml"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ConfigError):
        Config.load(str(p))


def test_division_from_segment():
    assert division_from_segment("КЦ") == "kc"
    assert division_from_segment("компрессор центр") == "kc"
    assert division_from_segment("Meyer") == "meyer"
    assert division_from_segment("") is None
    assert division_from_segment("непонятно") is None


# -- точка 3: диспетчер SMTP ---------------------------------------------------


def test_smtp_point_blocks_kc_mailbox_x_meyer_company(config, store, cards):
    _cid, _rid, mid = _seed(store, inn=MEYER_INN)
    sndr = _sender(config, store, cards)
    msg = store.get_message(mid)
    with pytest.raises(SuppressedError, match="division"):
        sndr.send(msg, _rendered(), "box1@rusprom.ru", now=datetime.now(UTC))
    assert store.get_message(mid).status == "skipped"
    evs = store.list_events(event_type="division_gate_block", limit=10)
    assert len(evs) == 1
    detail = evs[0].detail
    assert detail["inn"] == MEYER_INN and detail["mailbox"] == "box1@rusprom.ru"
    assert "mismatch" in detail["reason"] and detail["point"] == "smtp"


def test_smtp_point_blocks_mailbox_without_division(config, store, cards):
    _cid, _rid, mid = _seed(store, inn=KC_INN, mx="mailru")
    sndr = _sender(config, store, cards)
    msg = store.get_message(mid)
    with pytest.raises(SuppressedError, match="division"):
        sndr.send(msg, _rendered(), "box3@rusprom.ru", now=datetime.now(UTC))
    evs = store.list_events(event_type="division_gate_block", limit=10)
    assert "mailbox_without_division" in evs[0].detail["reason"]


def test_smtp_point_blocks_company_without_division(config, store, cards):
    _cid, _rid, mid = _seed(store, inn="7700000000")  # ИНН не из базы обзвона
    sndr = _sender(config, store, cards)
    msg = store.get_message(mid)
    with pytest.raises(SuppressedError, match="division"):
        sndr.send(msg, _rendered(), "box1@rusprom.ru", now=datetime.now(UTC))
    evs = store.list_events(event_type="division_gate_block", limit=10)
    assert "company_division_empty" in evs[0].detail["reason"]


def test_smtp_point_passes_matching_pair_and_manual_still_gated(
        config, store, cards):
    _cid, _rid, mid = _seed(store, inn=KC_INN)
    sndr = _sender(config, store, cards)
    sndr._deliver = lambda *a, **k: None  # сеть не нужна: проверяем гейт
    msg = store.get_message(mid)
    res = sndr.send(msg, _rendered(), "box1@rusprom.ru",
                    now=datetime.now(UTC), manual=True)
    assert res.ok  # совпадающая пара проходит (и в ручном режиме)
    _cid2, _rid2, mid2 = _seed_second(store, inn=MEYER_INN)
    msg2 = store.get_message(mid2)
    with pytest.raises(SuppressedError, match="division"):
        # ручная отправка гейт НЕ обходит — это комплаенс, не тайминг
        sndr.send(msg2, _rendered(), "box1@rusprom.ru",
                  now=datetime.now(UTC), manual=True)


def _seed_second(store, *, inn):
    cid = store.create_campaign(CampaignIn(
        name="Вторая", legal_entity="ООО «Руспром»", legal_inn="7700000000"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email="drugoy@fabrika.ru", domain="fabrika.ru", inn=inn))
    store.set_recipient_validation(rid, valid_status="valid", mx_provider="yandex")
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="m2", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=datetime.now(UTC)))
    return cid, rid, mid


# -- pick_mailbox: непригодный по направлению ящик не выбирается ---------------


def test_pick_mailbox_filters_by_division(config, store, cards):
    _cid, rid, _mid = _seed(store, inn=MEYER_INN)
    sndr = _sender(config, store, cards)
    recipient = store.get_recipient(rid)
    campaign = store.get_campaign(_cid)
    # Meyer-компания: в yandex-пуле только КЦ-ящики → выбрать некого
    assert sndr.pick_mailbox(recipient, campaign,
                             now=datetime.now(UTC)) is None


# -- точка 2: экран подтверждения ----------------------------------------------


def test_confirm_flags_and_approve_block_mismatch(config, store, cards):
    supp = Suppression(store)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     cards=cards)
    cid, rid, mid = _seed(store, inn=MEYER_INN)  # кампания КЦ × Meyer-компания
    r = cs.submit(email="klient@zavod.ru", inn=MEYER_INN, campaign_id=cid,
                  recipient_id=rid, message_id=mid, subject="s", body="b",
                  panel={"stop_flags": []})
    row = store.confirm_get(r.review_id)
    flags = row["panel"]["stop_flags"]
    assert any(f["code"] == "division_mismatch" for f in flags)
    assert row["panel"]["actions"]["confirm_hold"] is True
    with pytest.raises(ConfirmBlockedError, match="направлени"):
        cs.approve(r.review_id, operator="kirill")
    with pytest.raises(ConfirmBlockedError, match="направлени"):
        cs.edit(r.review_id, subject="правка", operator="kirill")


def test_confirm_flags_unknown_division(config, store, cards):
    supp = Suppression(store)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     cards=cards)
    cid, rid, mid = _seed(store, inn="7700000000")
    r = cs.submit(email="klient@zavod.ru", inn="7700000000", campaign_id=cid,
                  recipient_id=rid, message_id=mid, subject="s", body="b",
                  panel={"stop_flags": []})
    row = store.confirm_get(r.review_id)
    assert any(f["code"] == "division_unknown"
               for f in row["panel"]["stop_flags"])
    with pytest.raises(ConfirmBlockedError):
        cs.approve(r.review_id)


def test_confirm_matching_pair_passes(config, store, cards):
    supp = Suppression(store)
    cs = ConfirmSend(_Cfg(config, **{"confirm.mode": "all"}), store, supp,
                     cards=cards)
    cid, rid, mid = _seed(store, inn=KC_INN)
    r = cs.submit(email="klient@zavod.ru", inn=KC_INN, campaign_id=cid,
                  recipient_id=rid, message_id=mid, subject="s", body="b",
                  panel={"stop_flags": []})
    row = store.confirm_get(r.review_id)
    assert not any(str(f.get("code", "")).startswith("division")
                   for f in row["panel"]["stop_flags"])
    assert cs.approve(r.review_id, operator="kirill") is True


# -- точка 1: сборка очереди ---------------------------------------------------


class _FakeCadence:
    def __init__(self, msgs):
        self._msgs = msgs

    def plan_campaign(self, cid, *, now):
        return self._msgs


def test_queue_point_blocks(config, store, cards):
    from sender.orchestrator import Orchestrator
    cid, rid, _ = _seed(store, inn=MEYER_INN)   # кампания «КЦ база»
    msg_in = MessageIn(idempotency_key="q1", campaign_id=cid, recipient_id=rid,
                       sequence_step_id=1, scheduled_at=datetime.now(UTC))
    orch = Orchestrator(
        config=config, store=store, sender=_sender(config, store, cards),
        cadence=_FakeCadence([msg_in]), gates=_Gates(),
        imap=None, warmup=None, analytics=None, cards=cards)
    campaign = store.get_campaign(cid)
    # Meyer-компания в КЦ-кампании → блок на этапе очереди
    assert orch._division_queue_block(msg_in, campaign) is not None
    # компания без направления → блок
    rid2 = store.upsert_recipient(RecipientIn(
        email="x@y.ru", domain="y.ru", inn="7700000000"))
    msg2 = MessageIn(idempotency_key="q2", campaign_id=cid, recipient_id=rid2,
                     sequence_step_id=1, scheduled_at=datetime.now(UTC))
    assert orch._division_queue_block(msg2, campaign) == "company_division_empty"
    # совпадающая пара → пропуск
    rid3 = store.upsert_recipient(RecipientIn(
        email="ok@zavod2.ru", domain="zavod2.ru", inn=KC_INN))
    msg3 = MessageIn(idempotency_key="q3", campaign_id=cid, recipient_id=rid3,
                     sequence_step_id=1, scheduled_at=datetime.now(UTC))
    assert orch._division_queue_block(msg3, campaign) is None


def test_gate_sleeps_without_index(config, store):
    """Без индекса обзвона (песочница) гейт молчит — поведение прежнее."""
    inactive = CompanyCards(index_path=None)
    _cid, _rid, mid = _seed(store, inn=MEYER_INN)
    sndr = _sender(config, store, inactive)
    sndr._deliver = lambda *a, **k: None  # сеть не нужна: проверяем гейт
    msg = store.get_message(mid)
    res = sndr.send(msg, _rendered(), "box1@rusprom.ru",
                    now=datetime.now(UTC), manual=True)
    assert res.ok
