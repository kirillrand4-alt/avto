"""P1.6: баллы приоритета из базы обзвона + фазовый порядок отправки.

Импортёр тянет «Макс. балл по связке» / «Итоговый балл приоритета» /
«Приоритет × выручка / 10000» (PxR); кампания задаёт send_order
(pilot_asc | priority_desc) и порог min_priority_max в config_json;
plan_campaign планирует в этом порядке. Старые БД мигрируются ALTER-ами
в init_schema (боевая база на C:\\sender переживает обновление).
"""

import os
import sqlite3
from datetime import datetime, timezone

import pytest

from sender.cadence import Cadence
from sender.config import Config
from sender.importer import import_csv
from sender.store import CampaignIn, RecipientIn, SequenceStepIn, Store
from sender.suppression import Suppression
from sender.tests.test_config import BASE_YAML

NOW = datetime(2026, 7, 20, 9, 30, tzinfo=timezone.utc)  # пн, окно открыто


@pytest.fixture
def store(tmp_path):
    st = Store(str(tmp_path / "prio.db"))
    st.init_schema()
    return st


# --------------------------------------------------------------------------- #
# 1. Импортёр: автодетект реальных заголовков базы обзвона
# --------------------------------------------------------------------------- #

def test_import_priority_columns(store, tmp_path):
    csv_path = tmp_path / "base.csv"
    csv_path.write_text(
        "Email;Сегмент;Макс. балл по связке;Итоговый балл приоритета;"
        "Приоритет × выручка / 10000\n"
        "a@x.ru;кц;5;12,5;1 234,56\n"
        "b@y.ru;кц;3;7;89\n"
        "c@z.ru;кц;;;\n",  # без баллов — валидная строка
        encoding="utf-8",
    )
    result = import_csv(store, str(csv_path))
    assert result["imported"] == 3

    by_email = {r.email: r for r in store.iter_recipients()}
    a = by_email["a@x.ru"]
    assert a.priority_max == 5
    assert a.priority_total == 12.5
    assert a.pxr == 1234.56  # пробел-разделитель тысяч и запятая распарсены
    b = by_email["b@y.ru"]
    assert b.priority_max == 3 and b.pxr == 89.0
    c = by_email["c@z.ru"]
    assert c.priority_max is None and c.pxr is None


# --------------------------------------------------------------------------- #
# 2. iter_recipients: порядок по PxR и порог балла
# --------------------------------------------------------------------------- #

def _seed(store):
    rows = [
        ("low@x.ru", 2, 10.0),
        ("mid@x.ru", 4, 500.0),
        ("top@x.ru", 5, 9000.0),
        ("nul@x.ru", None, None),  # без баллов
    ]
    ids = {}
    for email, pmax, pxr in rows:
        rid = store.upsert_recipient(RecipientIn(
            email=email, domain="x.ru", segment="кц",
            priority_max=pmax, pxr=pxr))
        store.set_recipient_validation(rid, valid_status="valid")
        ids[email] = rid
    return ids


def test_iter_order_pxr(store):
    _seed(store)
    asc = [r.email for r in store.iter_recipients(order="pxr_asc")]
    # NULL pxr считается 0 -> первым в возрастании
    assert asc == ["nul@x.ru", "low@x.ru", "mid@x.ru", "top@x.ru"]
    desc = [r.email for r in store.iter_recipients(order="pxr_desc")]
    assert desc == ["top@x.ru", "mid@x.ru", "low@x.ru", "nul@x.ru"]


def test_iter_min_priority_threshold(store):
    _seed(store)
    got = {r.email for r in store.iter_recipients(min_priority_max=4)}
    # балл 2 отсечён; БЕЗ балла (NULL) проходит: нет оценки != плохая оценка
    assert got == {"mid@x.ru", "top@x.ru", "nul@x.ru"}


# --------------------------------------------------------------------------- #
# 3. plan_campaign: фазовый порядок и порог из config_json кампании
# --------------------------------------------------------------------------- #

@pytest.fixture
def cadence_env(tmp_path):
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    yaml_text = BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "c.db"))
    yaml_text += "\ncadence:\n  canary_size: 0\n"
    (tmp_path / "c.yaml").write_text(yaml_text, encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    st = Store(str(tmp_path / "c.db"))
    st.init_schema()
    return st, Cadence(config, st, Suppression(st))


def _campaign(store, **cfg):
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841",
        config=cfg))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, subject_tmpl="s", body_tmpl="b",
        delay_hours=0))
    store.set_campaign_status(cid, "active")
    return cid


def test_plan_priority_desc_order(cadence_env):
    store, cadence = cadence_env
    ids = _seed(store)
    cid = _campaign(store, send_order="priority_desc")
    planned = cadence.plan_campaign(cid, now=NOW)
    order = [m.recipient_id for m in planned]
    assert order[:3] == [ids["top@x.ru"], ids["mid@x.ru"], ids["low@x.ru"]]


def test_plan_pilot_asc_order(cadence_env):
    store, cadence = cadence_env
    ids = _seed(store)
    cid = _campaign(store, send_order="pilot_asc")
    order = [m.recipient_id for m in cadence.plan_campaign(cid, now=NOW)]
    # обкатка: дешёвые первыми (NULL=0 в голове)
    assert order == [ids["nul@x.ru"], ids["low@x.ru"], ids["mid@x.ru"],
                     ids["top@x.ru"]]


def test_plan_min_priority_excludes_low(cadence_env):
    store, cadence = cadence_env
    ids = _seed(store)
    cid = _campaign(store, min_priority_max=4)
    planned = {m.recipient_id for m in cadence.plan_campaign(cid, now=NOW)}
    assert ids["low@x.ru"] not in planned
    assert planned == {ids["mid@x.ru"], ids["top@x.ru"], ids["nul@x.ru"]}


def test_plan_default_order_unchanged(cadence_env):
    # Без send_order — по id, как раньше (обратная совместимость).
    store, cadence = cadence_env
    ids = _seed(store)
    cid = _campaign(store)
    order = [m.recipient_id for m in cadence.plan_campaign(cid, now=NOW)]
    assert order == sorted(ids.values())


# --------------------------------------------------------------------------- #
# 4. Миграция: старая БД (без колонок приоритета) переживает init_schema
# --------------------------------------------------------------------------- #

def test_init_schema_migrates_old_db(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    # Схема recipients ДО P1.6 (как на боевом C:\sender)
    conn.executescript("""
        CREATE TABLE recipients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inn TEXT, email TEXT NOT NULL, domain TEXT NOT NULL,
            company_name TEXT, okved TEXT, segment TEXT, bitrix_id TEXT,
            contact_name TEXT, mx_provider TEXT,
            valid_status TEXT NOT NULL DEFAULT 'unknown',
            catch_all INTEGER, role_based INTEGER, disposable INTEGER,
            source TEXT, extra_json TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX ux_recipients_email ON recipients(email);
        INSERT INTO recipients (email, domain, valid_status, created_at, updated_at)
        VALUES ('old@x.ru', 'x.ru', 'valid',
                '2026-01-01T00:00:00.000000', '2026-01-01T00:00:00.000000');
    """)
    conn.commit()
    conn.close()

    st = Store(str(db))
    st.init_schema()  # ALTER-ы добавляют колонки, старые данные живы
    old = next(r for r in st.iter_recipients() if r.email == "old@x.ru")
    assert old.priority_max is None and old.pxr is None
    # и новые записи с баллами пишутся
    rid = st.upsert_recipient(RecipientIn(
        email="new@x.ru", domain="x.ru", priority_max=5, pxr=777.0))
    assert st.get_recipient(rid).pxr == 777.0
