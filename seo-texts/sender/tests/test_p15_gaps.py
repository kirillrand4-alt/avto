"""P1.5.2-5: пробелы сценария владельца (PANEL-HOWTO).

Покрывает: импорт региона/таймзоны (+CSV из панели с default_segment), карту
регионов РФ -> IANA-зона, окно «с 9:00 по зоне ПОЛУЧАТЕЛЯ» в cadence,
пер-регион пейсинг в sender, эндпоинт POST /recipients/import.
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from sender.cadence import Cadence
from sender.config import Config
from sender.errors import RateLimitExceeded
from sender.importer import import_csv
from sender.regions import region_to_tz
from sender.store import (
    CampaignIn, EventIn, MessageIn, RecipientIn, SequenceStepIn, Store,
)
from sender.suppression import Suppression
from sender.tests.test_config import BASE_YAML

# Пн 09:30 UTC = 12:30 МСК (внутри окна 09-18 МСК BASE_YAML)
NOW = datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc)


def _env():
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32


@pytest.fixture
def store(tmp_path):
    st = Store(str(tmp_path / "p15.db"))
    st.init_schema()
    return st


@pytest.fixture
def config(tmp_path):
    _env()
    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "p15.db"))
    yaml_text += "\ncadence:\n  canary_size: 0\n"
    (tmp_path / "c.yaml").write_text(yaml_text, encoding="utf-8")
    return Config.load(str(tmp_path / "c.yaml"))


# --------------------------------------------------------------------------- #
# 1. Карта регионов РФ -> таймзона
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("region,tz", [
    ("Москва", "Europe/Moscow"),
    ("г. Москва", "Europe/Moscow"),
    ("Московская обл.", "Europe/Moscow"),
    ("Респ. Татарстан", "Europe/Moscow"),
    ("Новосибирская область", "Asia/Novosibirsk"),
    ("Приморский край", "Asia/Vladivostok"),
    ("Свердловская область", "Asia/Yekaterinburg"),
    ("Калининградская область", "Europe/Kaliningrad"),
    ("Омская область", "Asia/Omsk"),
    ("Томская область", "Asia/Tomsk"),  # 'томск' не съедается 'омск'-ом
    ("Самарская область", "Europe/Samara"),
    ("Камчатский край", "Asia/Kamchatka"),
    ("", None),
    (None, None),
    ("Гондор", None),
])
def test_region_to_tz(region, tz):
    assert region_to_tz(region) == tz


# --------------------------------------------------------------------------- #
# 2. Импортёр: регион/таймзона/default_segment
# --------------------------------------------------------------------------- #

def test_import_region_tz_and_default_segment(store, tmp_path):
    csv_path = tmp_path / "base.csv"
    csv_path.write_text(
        "Email;Регион;Таймзона\n"
        "a@x.ru;Новосибирская область;\n"      # tz выводится из региона
        "b@y.ru;Москва;Asia/Vladivostok\n"     # явная колонка tz ПОБЕЖДАЕТ регион
        "c@z.ru;;\n",                          # без региона -> оба None
        encoding="utf-8",
    )
    result = import_csv(store, str(csv_path), default_segment="кц")
    assert result["imported"] == 3

    by = {r.email: r for r in store.iter_recipients()}
    assert by["a@x.ru"].region == "Новосибирская область"
    assert by["a@x.ru"].tz == "Asia/Novosibirsk"
    assert by["b@y.ru"].tz == "Asia/Vladivostok"  # явное значение не перетёрто
    assert by["c@z.ru"].region is None and by["c@z.ru"].tz is None
    # default_segment применился ко всем строкам без своего сегмента (панель)
    assert {r.segment for r in by.values()} == {"кц"}


def test_import_csv_segment_column_beats_default(store, tmp_path):
    csv_path = tmp_path / "seg.csv"
    csv_path.write_text(
        "Email;Сегмент\nmeyer1@x.ru;meyer\nkc1@x.ru;\n", encoding="utf-8")
    import_csv(store, str(csv_path), default_segment="кц")
    by = {r.email: r.segment for r in store.iter_recipients()}
    assert by == {"meyer1@x.ru": "meyer", "kc1@x.ru": "кц"}


# --------------------------------------------------------------------------- #
# 3. Cadence: окно 9:00 в зоне получателя
# --------------------------------------------------------------------------- #

def _seed_recipient(store, email, tz=None):
    rid = store.upsert_recipient(RecipientIn(
        email=email, domain=email.split("@")[1], tz=tz))
    store.set_recipient_validation(rid, valid_status="valid")
    return rid


def _campaign_with_step(store):
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, subject_tmpl="s", body_tmpl="b",
        delay_hours=0))
    store.set_campaign_status(cid, "active")
    return cid


def test_window_in_recipient_timezone(store, config):
    """NOW=09:30 UTC: в МСК это 12:30 (окно открыто), во Владивостоке 19:30 —
    письмо владивостокцу обязано уехать на следующее утро 9:00 ПО МЕСТНОМУ."""
    cadence = Cadence(store=store, config=config, suppression=Suppression(store))
    cid = _campaign_with_step(store)
    rid_msk = _seed_recipient(store, "msk@x.ru", tz=None)
    rid_vld = _seed_recipient(store, "vld@x.ru", tz="Asia/Vladivostok")

    planned = {m.recipient_id: m for m in cadence.plan_campaign(cid, now=NOW)}

    msk_local = planned[rid_msk].scheduled_at.astimezone(ZoneInfo("Europe/Moscow"))
    assert (msk_local.hour, msk_local.minute) == (12, 30)  # окно открыто, без сдвига

    vld_local = planned[rid_vld].scheduled_at.astimezone(ZoneInfo("Asia/Vladivostok"))
    # старт окна BASE_YAML = 09:30 по МЕСТНОМУ времени получателя, след. день
    assert (vld_local.hour, vld_local.minute) == (9, 30)
    assert vld_local.date() > NOW.astimezone(ZoneInfo("Asia/Vladivostok")).date()
    assert planned[rid_vld].scheduled_at > planned[rid_msk].scheduled_at


def test_broken_tz_falls_back_to_config_window(store, config):
    cadence = Cadence(store=store, config=config, suppression=Suppression(store))
    cid = _campaign_with_step(store)
    rid = _seed_recipient(store, "bad@x.ru", tz="Mars/Olympus")
    planned = cadence.plan_campaign(cid, now=NOW)
    local = planned[0].scheduled_at.astimezone(ZoneInfo("Europe/Moscow"))
    assert planned[0].recipient_id == rid
    assert (local.hour, local.minute) == (12, 30)  # зона конфига, не падение


# --------------------------------------------------------------------------- #
# 4. Sender: пейсинг по региону
# --------------------------------------------------------------------------- #

def _sender_env(tmp_path, region_gap):
    _env()
    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "s.db"))
    yaml_text += ("\nsend_pacing:\n  min_interval_sec: 0\n  max_interval_sec: 0\n"
                  f"  per_region_interval_sec: {region_gap}\n")
    (tmp_path / "s.yaml").write_text(yaml_text, encoding="utf-8")
    config = Config.load(str(tmp_path / "s.yaml"))
    store = Store(str(tmp_path / "s.db"))
    store.init_schema()

    from sender.gates import Gates
    from sender.sender import Sender
    suppression = Suppression(store)
    sender = Sender(config, store, suppression, Gates(config, store), dry_run=True)
    sender._deliver = lambda *a, **k: None  # SMTP не нужен: проверяем гейты
    # mailbox_state нужен increment_sent на фиксации успеха
    from sender.store import MailboxState
    for mb in config.mailboxes():
        store.upsert_mailbox_state(MailboxState(
            mailbox_id=mb.mailbox_id, provider=mb.provider,
            day_key=sender._day_key(NOW), sent_today=0, sent_total=0,
            ramp_day=1, daily_limit=100, last_sent_at=None,
            paused=False, pause_reason=None))
    return config, store, sender


def _seed_message(store, email, region):
    rid = store.upsert_recipient(RecipientIn(
        email=email, domain=email.split("@")[1], region=region))
    store.set_recipient_validation(rid, valid_status="valid")
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, subject_tmpl="s", body_tmpl="b",
        delay_hours=0))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=f"p15-{email}", campaign_id=cid, recipient_id=rid,
        sequence_step_id=sid, scheduled_at=NOW))
    return store.get_message(mid), rid


def _rendered():
    from types import SimpleNamespace
    return SimpleNamespace(subject="Тема", body="텍ст", unfilled_fields=(), used_ai=False)


def _first_mailbox(config):
    return config.mailboxes()[0].mailbox_id


def test_region_pacing_blocks_within_interval(tmp_path):
    config, store, sender = _sender_env(tmp_path, region_gap=300)
    msg, _rid = _seed_message(store, "a@x.ru", region="Новосибирская область")
    # минуту назад в ЭТОТ регион уже слали (другому получателю)
    other_rid = store.upsert_recipient(RecipientIn(
        email="prev@x.ru", domain="x.ru", region="Новосибирская область"))
    store.append_event(EventIn(
        dedup_key="prev-sent", event_type="sent",
        event_ts=NOW.replace(minute=29), recipient_id=other_rid))

    with pytest.raises(RateLimitExceeded, match="region"):
        sender.send(msg, _rendered(), _first_mailbox(config), now=NOW)


def test_region_pacing_allows_other_region_and_after_interval(tmp_path):
    config, store, sender = _sender_env(tmp_path, region_gap=300)
    msg, _rid = _seed_message(store, "a@x.ru", region="Омская область")
    other_rid = store.upsert_recipient(RecipientIn(
        email="prev@x.ru", domain="x.ru", region="Новосибирская область"))
    store.append_event(EventIn(
        dedup_key="prev-sent", event_type="sent",
        event_ts=NOW.replace(minute=29), recipient_id=other_rid))
    # другой регион — не блокируется
    assert sender.send(msg, _rendered(), _first_mailbox(config), now=NOW).ok


def test_region_pacing_disabled_by_default(tmp_path):
    config, store, sender = _sender_env(tmp_path, region_gap=0)
    msg, _rid = _seed_message(store, "a@x.ru", region="Новосибирская область")
    other_rid = store.upsert_recipient(RecipientIn(
        email="prev@x.ru", domain="x.ru", region="Новосибирская область"))
    store.append_event(EventIn(
        dedup_key="prev-sent", event_type="sent",
        event_ts=NOW.replace(minute=29, second=59), recipient_id=other_rid))
    assert sender.send(msg, _rendered(), _first_mailbox(config), now=NOW).ok


# --------------------------------------------------------------------------- #
# 5. API: импорт CSV из панели
# --------------------------------------------------------------------------- #

fastapi = pytest.importorskip("fastapi")


def test_api_import_endpoint(tmp_path):
    from fastapi.testclient import TestClient
    from sender.api.app import build_deps, make_app

    _env()
    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "api.db"))
    (tmp_path / "c.yaml").write_text(yaml_text, encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    store = Store(str(tmp_path / "api.db"))
    store.init_schema()
    deps = build_deps(config, store)
    deps.auth.create_user(username="owner", password="ownerpass", role="owner")
    deps.auth.create_user(username="mgr", password="mgrpass", role="manager")
    c = TestClient(make_app(deps))

    def tok(u, p):
        return c.post("/auth/login", json={"username": u, "password": p}).json()["token"]

    hdr_o = {"Authorization": f"Bearer {tok('owner', 'ownerpass')}"}
    csv_body = "Email;Регион\nimp1@x.ru;Москва\nimp2@y.ru;Омская область\n".encode("utf-8")

    # менеджеру нельзя
    hdr_m = {"Authorization": f"Bearer {tok('mgr', 'mgrpass')}"}
    assert c.post("/recipients/import?segment=кц", content=csv_body,
                  headers=hdr_m).status_code == 403

    r = c.post("/recipients/import?segment=кц", content=csv_body, headers=hdr_o)
    assert r.status_code == 200, r.text
    import_id = r.json()["import_id"]

    # фон-поток быстрый на 2 строках; подождём завершения статусом
    import time
    for _ in range(100):
        st = c.get(f"/recipients/import/{import_id}", headers=hdr_o).json()
        if st["done"]:
            break
        time.sleep(0.05)
    assert st["done"] and st["error"] is None, st
    assert st["imported"] == 2

    emails = {r.email: r for r in store.iter_recipients()}
    assert emails["imp1@x.ru"].segment == "кц"
    assert emails["imp1@x.ru"].tz == "Europe/Moscow"
    assert emails["imp2@y.ru"].tz == "Asia/Omsk"
    # пустое тело -> 400; чужой id -> 404
    assert c.post("/recipients/import", content=b"", headers=hdr_o).status_code == 400
    assert c.get("/recipients/import/nope", headers=hdr_o).status_code == 404
    # аудит записан
    assert any(a["action"] == "recipients.import" for a in store.list_audit())
