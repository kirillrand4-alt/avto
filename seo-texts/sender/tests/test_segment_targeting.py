"""Таргетинг кампании по сегменту (P1.5.1, БЛОКЕР сценария владельца).

До правки cadence.plan_campaign брал iter_recipients(valid_status='valid') без
фильтра — КАЖДАЯ кампания била по всей базе (КЦ + Meyer вместе). Теперь кампания
несёт целевой сегмент в config_json ({"segment": "кц"}), plan_campaign фильтрует.
Интеграционно, на реальном Store: сидим 2 сегмента и проверяем разводку.
"""

import os
from datetime import datetime, timezone

import pytest

from sender.cadence import Cadence
from sender.config import Config
from sender.store import CampaignIn, RecipientIn, SequenceStepIn, Store
from sender.suppression import Suppression
from sender.tests.test_config import BASE_YAML

# Пн 09:30 UTC (внутри окна отправки BASE_YAML), фиксировано для детерминизма.
NOW = datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path):
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "seg.db"))
    # Канарейку выключаем: тест про таргетинг, а не про волны.
    yaml_text += "\ncadence:\n  canary_size: 0\n"
    (tmp_path / "c.yaml").write_text(yaml_text, encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    store = Store(str(tmp_path / "seg.db"))
    store.init_schema()

    ids = {}
    for email, seg in [
        ("kc1@zavod-a.ru", "кц"), ("kc2@zavod-b.ru", "кц"),
        ("m1@fish-plant.ru", "meyer"), ("m2@meat-plant.ru", "meyer"),
    ]:
        rid = store.upsert_recipient(RecipientIn(
            email=email, domain=email.split("@")[1], segment=seg))
        store.set_recipient_validation(rid, valid_status="valid")
        ids[email] = rid
    cadence = Cadence(config, store, Suppression(store))
    return store, cadence, ids


def _make_campaign(store, segment):
    cfg = {"segment": segment} if segment else {}
    cid = store.create_campaign(CampaignIn(
        name=f"c-{segment or 'all'}", legal_entity="ООО «Руспром»",
        legal_inn="2221239841", config=cfg))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, subject_tmpl="s", body_tmpl="b",
        delay_hours=0))
    store.set_campaign_status(cid, "active")
    return cid


def test_kc_campaign_does_not_touch_meyer(env):
    store, cadence, ids = env
    cid = _make_campaign(store, "кц")
    planned = cadence.plan_campaign(cid, now=NOW)
    planned_rids = {m.recipient_id for m in planned}
    assert planned_rids == {ids["kc1@zavod-a.ru"], ids["kc2@zavod-b.ru"]}
    assert ids["m1@fish-plant.ru"] not in planned_rids
    assert ids["m2@meat-plant.ru"] not in planned_rids


def test_meyer_campaign_symmetric(env):
    store, cadence, ids = env
    cid = _make_campaign(store, "meyer")
    planned_rids = {m.recipient_id for m in cadence.plan_campaign(cid, now=NOW)}
    assert planned_rids == {ids["m1@fish-plant.ru"], ids["m2@meat-plant.ru"]}


def test_campaign_without_segment_plans_all(env):
    # Обратная совместимость: без сегмента — вся база (поведение как раньше).
    store, cadence, ids = env
    cid = _make_campaign(store, None)
    planned_rids = {m.recipient_id for m in cadence.plan_campaign(cid, now=NOW)}
    assert planned_rids == set(ids.values())


def test_unknown_segment_plans_nobody(env):
    # Опечатка в сегменте не должна тихо превращаться в «слать всем».
    store, cadence, ids = env
    cid = _make_campaign(store, "нет-такого")
    assert cadence.plan_campaign(cid, now=NOW) == []


def test_iter_recipients_segment_filter(env):
    store, _, ids = env
    got = {r.email for r in store.iter_recipients(segment="кц")}
    assert got == {"kc1@zavod-a.ru", "kc2@zavod-b.ru"}
    # без фильтра — все
    assert len(list(store.iter_recipients())) == 4
