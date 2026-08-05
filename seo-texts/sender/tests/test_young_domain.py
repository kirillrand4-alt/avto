# FILE: sender/tests/test_young_domain.py
"""Гейт молодых доменов (решение владельца 05.08.2026).

Урок трёх отбивок 05.08: ЕвроХим («poor reputation of a domain»), ТАИФ-НК и
Эл5-Энерго — все с СОБСТВЕННЫХ корп. серверов, всем нашим доменам 9–15 дней.
Правило: получатель на своём сервере (mx_provider other/unknown) + домену
ящика-отправителя меньше min_age_days → не отправлять и не планировать.
Публичные провайдеры (mailru/yandex/…) не трогаем; force открывает; после
созревания домена гейт отпускает сам.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.cadence import Cadence  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import (  # noqa: E402
    CampaignIn, MailboxState, MessageIn, RecipientIn, SequenceStepIn,
)
from sender.errors import GateTrippedError, YoungDomainGateError  # noqa: E402
from sender.gates import (  # noqa: E402
    young_domain_all_blocked, young_domain_reason,
)
from sender.sender import RenderedMessage, Sender  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.suppression import Suppression  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class _Cfg:
    """Мини-конфиг: словарь с точечными ключами + список ящиков."""

    def __init__(self, data=None, mailboxes=()):
        self._d = dict(data or {})
        self._mb = list(mailboxes)

    def get(self, key, default=None):
        node = self._d
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return default
        return node

    def mailboxes(self):
        return self._mb


def _cfg(min_days=30, domains=None, providers=None, mailboxes=()):
    yd = {"min_age_days": min_days}
    if domains is not None:
        yd["domains"] = domains
    if providers is not None:
        yd["providers"] = providers
    return _Cfg({"gates": {"young_domain": yd}}, mailboxes)


YOUNG = {"rusprom.ru": "2026-07-21"}          # 15 дней к NOW
AGED = {"rusprom.ru": "2026-06-01"}           # 65 дней к NOW


# --- young_domain_reason ---------------------------------------------------

def test_vyklyuchen_bez_konfiga():
    assert young_domain_reason(_Cfg(), "b@rusprom.ru", "other", now=NOW) is None


def test_molodoy_domen_i_korp_server_blok():
    r = young_domain_reason(_cfg(domains=YOUNG), "b@rusprom.ru", "other", now=NOW)
    assert r is not None and "rusprom.ru" in r and "15" in r
    # в причине — дата, с которой можно слать (21.07 + 30 дней)
    assert "2026-08-20" in r


def test_publichnyi_provayder_prohodit():
    for prov in ("mailru", "yandex", "google", "outlook", "vk"):
        assert young_domain_reason(
            _cfg(domains=YOUNG), "b@rusprom.ru", prov, now=NOW) is None


def test_sozrevshiy_domen_prohodit():
    assert young_domain_reason(
        _cfg(domains=AGED), "b@rusprom.ru", "other", now=NOW) is None


def test_granitsa_rovno_min_age():
    """Ровно 30 дней = зрелый (age >= min)."""
    cfg = _cfg(domains={"rusprom.ru": "2026-07-06"})  # 30 дней к NOW
    assert young_domain_reason(cfg, "b@rusprom.ru", "other", now=NOW) is None


def test_pustoy_provayder_schitaetsya_unknown():
    """Не валидировано (None/'') = unknown: не знаем сервер — держим."""
    for prov in (None, "", "  "):
        assert young_domain_reason(
            _cfg(domains=YOUNG), "b@rusprom.ru", prov, now=NOW) is not None


def test_domen_ne_v_spiske_schitaetsya_zrelym():
    assert young_domain_reason(
        _cfg(domains=YOUNG), "b@drugoy.ru", "other", now=NOW) is None


def test_bitaya_data_ne_ronyaet():
    cfg = _cfg(domains={"rusprom.ru": "не дата"})
    assert young_domain_reason(cfg, "b@rusprom.ru", "other", now=NOW) is None


def test_svoi_providery_iz_konfiga():
    cfg = _cfg(domains=YOUNG, providers=["other"])
    assert young_domain_reason(cfg, "b@rusprom.ru", "unknown", now=NOW) is None
    assert young_domain_reason(cfg, "b@rusprom.ru", "other", now=NOW) is not None


# --- young_domain_all_blocked ----------------------------------------------

def test_all_blocked_kogda_vse_molodye():
    cfg = _cfg(domains=YOUNG)
    r = young_domain_all_blocked(
        cfg, ["a@rusprom.ru", "b@rusprom.ru"], "other", now=NOW)
    assert r is not None and "у всех 2 ящиков" in r


def test_odin_zrelyi_yashchik_otkryvaet_plan():
    cfg = _cfg(domains={"rusprom.ru": "2026-07-21", "staryi.ru": "2020-01-01"})
    assert young_domain_all_blocked(
        cfg, ["a@rusprom.ru", "b@staryi.ru"], "other", now=NOW) is None


def test_bez_yashchikov_ne_blokiruet():
    assert young_domain_all_blocked(_cfg(domains=YOUNG), [], "other", now=NOW) is None


# --- интеграция: sender.send ----------------------------------------------

class _Gates:
    def check_global(self):
        return type("D", (), {"tripped": False})()
    check_domain = lambda self, *a, **k: type("D", (), {"tripped": False})()  # noqa: E731
    check_mailbox = lambda self, *a, **k: type("D", (), {"tripped": False})()  # noqa: E731


class _Over:
    """Реальный Config + оверлей ключей гейта (как _Cfg в test_division_gate)."""

    def __init__(self, base, over):
        self._base, self._over = base, over

    def get(self, key, default=None):
        node = self._over
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return self._base.get(key, default)
        return node

    def __getattr__(self, name):
        return getattr(self._base, name)


@pytest.fixture
def config(tmp_path):
    for i in range(1, 6):
        os.environ[f"BOX{i}_PASSWORD"] = "secret"
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    yaml = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "t.db"))
    path = tmp_path / "c.yaml"
    path.write_text(yaml, encoding="utf-8")
    return Config.load(str(path))


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.init_schema()
    yield s
    s.close()


def _seed(store, *, mx="other"):
    cid = store.create_campaign(CampaignIn(
        name="КЦ база", legal_entity="ООО «Руспром»", legal_inn="2221239841",
        config={"segment": "КЦ"}))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    rid = store.upsert_recipient(RecipientIn(
        email="klient@zavod.ru", domain="zavod.ru", inn="4201000625",
        segment="КЦ"))
    store.set_recipient_validation(rid, valid_status="valid", mx_provider=mx)
    for i in range(1, 6):
        mb = f"box{i}@rusprom.ru"
        store.upsert_mailbox_state(MailboxState(
            mailbox_id=mb, provider="yandex" if i <= 2 else "mailru",
            day_key=NOW.strftime("%Y-%m-%d"),
            sent_today=0, sent_total=0, ramp_day=60, daily_limit=200,
            last_sent_at=None, paused=False, pause_reason=None))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key="m1", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=NOW))
    return cid, rid, mid


def _young_over(config):
    return _Over(config, {"gates": {"young_domain": {
        "min_age_days": 30, "domains": {"rusprom.ru": "2026-07-21"}}}})


def test_send_derzhit_molodoy_domen_i_ne_ubivaet_pismo(config, store):
    cid, rid, mid = _seed(store, mx="other")
    sender = Sender(_young_over(config), store, Suppression(store), _Gates(),
                    dry_run=True)
    msg = store.get_message(mid)
    with pytest.raises(YoungDomainGateError):
        sender.send(msg, RenderedMessage(subject="Т", body="Б",
                                         unfilled_fields=()),
                    "box1@rusprom.ru", now=NOW, manual=True)
    # письмо ЖИВОЕ: не skipped и не failed — после созревания уйдёт как есть
    after = store.get_message(mid)
    assert after.status not in ("skipped", "failed")


def test_yavlyaetsya_gate_tripped_dlya_starykh_obrabotchikov(config, store):
    _, _, mid = _seed(store, mx="other")
    sender = Sender(_young_over(config), store, Suppression(store), _Gates(),
                    dry_run=True)
    with pytest.raises(GateTrippedError):
        sender.send(store.get_message(mid),
                    RenderedMessage(subject="Т", body="Б", unfilled_fields=()),
                    "box1@rusprom.ru", now=NOW, manual=True)


def test_force_otkryvaet_otpravku(config, store):
    _, _, mid = _seed(store, mx="other")
    sender = Sender(_young_over(config), store, Suppression(store), _Gates(),
                    dry_run=True)
    sender._deliver = lambda *a, **k: None  # сеть не нужна: проверяем гейт
    res = sender.send(store.get_message(mid),
                      RenderedMessage(subject="Т", body="Б", unfilled_fields=()),
                      "box1@rusprom.ru", now=NOW, manual=True, force=True)
    assert res.ok


def test_publichnyi_poluchatel_prokhodit_send(config, store):
    _, _, mid = _seed(store, mx="mailru")
    sender = Sender(_young_over(config), store, Suppression(store), _Gates(),
                    dry_run=True)
    sender._deliver = lambda *a, **k: None  # сеть не нужна: проверяем гейт
    res = sender.send(store.get_message(mid),
                      RenderedMessage(subject="Т", body="Б", unfilled_fields=()),
                      "box1@rusprom.ru", now=NOW, manual=True)
    assert res.ok


def test_bez_konfiga_povedenie_prezhnee(config, store):
    _, _, mid = _seed(store, mx="other")
    sender = Sender(config, store, Suppression(store), _Gates(), dry_run=True)
    sender._deliver = lambda *a, **k: None  # сеть не нужна: проверяем гейт
    res = sender.send(store.get_message(mid),
                      RenderedMessage(subject="Т", body="Б", unfilled_fields=()),
                      "box1@rusprom.ru", now=NOW, manual=True)
    assert res.ok


# --- интеграция: планирование (cadence) -----------------------------------

def test_plan_otkladyvaet_korp_poluchateley(config, store):
    cid, rid, _ = _seed(store, mx="other")
    cadence = Cadence(_young_over(config), store, Suppression(store))
    msgs = cadence.plan_campaign(cid, now=NOW)
    assert msgs == []  # корп. получатель отложен: все ящики молоды


def test_plan_beryot_publichnykh(config, store):
    cid, rid, _ = _seed(store, mx="mailru")
    cadence = Cadence(_young_over(config), store, Suppression(store))
    msgs = cadence.plan_campaign(cid, now=NOW)
    assert len(msgs) >= 1
