"""Задача 4: паритет CLI ↔ веб-панель для confirm-send.

Один и тот же сценарий калибровки прогоняется ДВАЖДЫ — через CLI-команды
(sender.cli.main) и через HTTP API (FastAPI TestClient) — и обязан дать
ИДЕНТИЧНОЕ состояние очереди/писем/стоп-листа (нормализованный дамп БД).
Оба интерфейса — представления над одним модулем sender.confirm.
"""

import json
import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sender.api.app import make_app  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.dtos import CampaignIn, MessageIn, RecipientIn, SequenceStepIn  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.wiring import build_deps  # noqa: E402
from sender import cli  # noqa: E402

OPERATOR = "kirill"
LETTERS = [
    {"email": "lead1@zavod.ru", "inn": "4201000625",
     "subject": "Сжатый воздух под проект", "body": "Тело 1"},
    {"email": "lead2@fabrika.ru", "inn": "5050029646",
     "subject": "Фотосепаратор под крупу", "body": "Тело 2"},
    {"email": "lead3@rival.ru", "inn": "7707049388",
     "subject": "Компрессор", "body": "Тело 3"},
]


def _mkconfig(tmp_path, name):
    os.environ.setdefault("BOX1_PASSWORD", "x")
    os.environ.setdefault("BOX2_PASSWORD", "x")
    os.environ.setdefault("BOX3_PASSWORD", "x")
    os.environ.setdefault("BOX4_PASSWORD", "x")
    os.environ.setdefault("BOX5_PASSWORD", "x")
    os.environ["UNSUB_SIGNING_SECRET"] = "test_secret_key_min_32_chars_long"
    db = tmp_path / f"{name}.db"
    yaml = BASE_YAML.replace("/tmp/sender.db", str(db))
    yaml += "\nconfirm:\n  mode: all\n"
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml, encoding="utf-8")
    return str(path), str(db)


def _seed(config_path, db_path):
    """Общий генерационный слой: кампания + письма в очередь подтверждений."""
    config = Config.load(config_path)
    store = Store(db_path)
    store.init_schema()
    deps = build_deps(config, store)
    cid = store.create_campaign(CampaignIn(
        name="Калибровка", legal_entity="ООО «Руспром»",
        legal_inn="2221239841"))
    sid = store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    from datetime import datetime, timezone
    for i, L in enumerate(LETTERS):
        rid = store.upsert_recipient(RecipientIn(
            email=L["email"], domain=L["email"].split("@")[1], inn=L["inn"]))
        mid, _ = store.enqueue_message(MessageIn(
            idempotency_key=f"cal:{L['email']}", campaign_id=cid,
            recipient_id=rid, sequence_step_id=sid,
            scheduled_at=datetime.now(timezone.utc)), status="pending_review")
        deps.confirm.submit(
            email=L["email"], inn=L["inn"], campaign_id=cid,
            recipient_id=rid, message_id=mid,
            subject=L["subject"], body=L["body"],
            panel={"scoring": {"score": 50 + i}})
    return deps, cid


def _dump_state(db_path):
    """Нормализованный дамп значимого состояния (без времени/ID)."""
    store = Store(db_path)
    store.init_schema()
    reviews = [
        {k: r.get(k) for k in ("email", "inn", "status", "reason",
                               "edited_subject", "edited_body", "diff_text",
                               "decided_by")}
        for r in sorted(store.confirm_list(limit=100),
                        key=lambda r: r["email"])
    ]
    with store._lock:
        messages = [
            dict(email=row["e"], status=row["status"], subject=row["subject"],
                 body=row["body_rendered"])
            for row in store._conn.execute(
                "SELECT r.email e, m.status, m.subject, m.body_rendered"
                "  FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                " ORDER BY r.email").fetchall()
        ]
        suppression = [
            dict(row) for row in store._conn.execute(
                "SELECT scope, value, reason FROM suppression"
                " ORDER BY scope, value").fetchall()
        ]
    store.close()
    return {"reviews": reviews, "messages": messages,
            "suppression": suppression}


def _scenario_via_cli(tmp_path):
    config_path, db_path = _mkconfig(tmp_path, "cli")
    deps, cid = _seed(config_path, db_path)
    ids = {r["email"]: r["id"] for r in deps.confirm.pending(limit=10)}
    deps.store.close()

    def run(*argv):
        rc = cli.main(["--config", config_path, *argv])
        assert rc == 0, f"cli {argv} -> rc={rc}"

    # решение 1: approve; 2: edit (правка тела); 3: stoplist конкурент
    run("confirm-decide", "approve", str(ids["lead1@zavod.ru"]),
        "--operator", OPERATOR)
    body_f = tmp_path / "edited.txt"
    body_f.write_text("Тело 2 — правка оператора", encoding="utf-8")
    run("confirm-decide", "edit", str(ids["lead2@fabrika.ru"]),
        "--body-file", str(body_f), "--operator", OPERATOR)
    run("confirm-decide", "stoplist", str(ids["lead3@rival.ru"]),
        "--reason", "конкурент", "--operator", OPERATOR)
    return _dump_state(db_path)


def _scenario_via_web(tmp_path):
    config_path, db_path = _mkconfig(tmp_path, "web")
    deps, cid = _seed(config_path, db_path)
    # оператор веб-панели тот же (паритет по decided_by)
    deps.auth.create_user(username=OPERATOR, password="password123",
                          role="owner")
    app = make_app(deps)
    client = TestClient(app)
    token = client.post("/auth/login", json={
        "username": OPERATOR, "password": "password123"}).json()["token"]
    hdr = {"Authorization": f"Bearer {token}"}

    queue = client.get("/confirm/queue", headers=hdr).json()["pending"]
    ids = {r["email"]: r["id"] for r in queue}

    def decide(rid, payload):
        resp = client.post(f"/confirm/{rid}/decision", json=payload,
                           headers=hdr)
        assert resp.status_code == 200, resp.text

    decide(ids["lead1@zavod.ru"], {"action": "approve"})
    decide(ids["lead2@fabrika.ru"],
           {"action": "edit", "body": "Тело 2 — правка оператора"})
    decide(ids["lead3@rival.ru"],
           {"action": "stoplist", "reason": "конкурент"})
    deps.store.close()
    return _dump_state(db_path)


def test_cli_and_web_produce_identical_state(tmp_path):
    state_cli = _scenario_via_cli(tmp_path)
    state_web = _scenario_via_web(tmp_path)
    assert json.dumps(state_cli, ensure_ascii=False, sort_keys=True) == \
        json.dumps(state_web, ensure_ascii=False, sort_keys=True)
    # и это не «пусто == пусто»: сценарий реально что-то сделал
    st = {r["email"]: r["status"] for r in state_cli["reviews"]}
    assert st == {"lead1@zavod.ru": "approved", "lead2@fabrika.ru": "edited",
                  "lead3@rival.ru": "stoplist"}
    assert any(s["reason"] == "competitor" for s in state_cli["suppression"])
    ms = {m["email"]: m for m in state_cli["messages"]}
    assert ms["lead1@zavod.ru"]["status"] == "scheduled"
    assert ms["lead2@fabrika.ru"]["body"] == "Тело 2 — правка оператора"
    assert ms["lead3@rival.ru"]["status"] == "skipped"


def test_web_blocked_approve_is_409_and_cli_rc2(tmp_path):
    """Заслон подтверждения одинаково виден в обоих интерфейсах."""
    config_path, db_path = _mkconfig(tmp_path, "block")
    deps, cid = _seed(config_path, db_path)
    rid = deps.confirm.pending(limit=1)[0]["id"]
    row = deps.confirm.get(rid)
    deps.suppression.add_email(row["email"], "unsubscribe")

    deps.auth.create_user(username=OPERATOR, password="password123",
                          role="owner")
    client = TestClient(make_app(deps))
    token = client.post("/auth/login", json={
        "username": OPERATOR, "password": "password123"}).json()["token"]
    resp = client.post(f"/confirm/{rid}/decision", json={"action": "approve"},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409
    deps.store.close()

    rc = cli.main(["--config", config_path, "confirm-decide", "approve",
                   str(rid), "--operator", OPERATOR])
    assert rc == 2  # ConfirmBlockedError — отдельный код возврата


def _added_contact_state(db_path, email):
    """Что осталось в базе после добавления контакта: карточка + строка
    получателя (без ID и времени — их сравнивать нельзя)."""
    store = Store(db_path)
    store.init_schema()
    reviews = [{"email": r["email"], "inn": r.get("inn"),
                "status": r["status"]}
               for r in sorted(store.confirm_list(limit=100),
                               key=lambda r: r["email"])]
    rec = store.find_recipient_by_email(email)
    contact = None if rec is None else {
        k: rec.get(k) for k in ("email", "inn", "company_name", "source")}
    store.close()
    return {"reviews": reviews, "contact": contact}


def test_add_recipient_parity_cli_web(tmp_path):
    """Ручное добавление контакта: CLI и панель дают ОДНО состояние базы.

    Пока команды в CLI не было, паритет по этой ручке был заявлен, но не
    выполнялся (PLAN-DOBAVIT-ADRES, п. 6.8).
    """
    новый = "snab@zavod.ru"

    # --- CLI ---
    config_cli, db_cli = _mkconfig(tmp_path, "addcli")
    deps, _cid = _seed(config_cli, db_cli)
    rid_cli = {r["email"]: r["id"] for r in deps.confirm.pending(limit=10)}[
        "lead1@zavod.ru"]
    deps.store.close()
    rc = cli.main(["--config", config_cli, "confirm-recipient", str(rid_cli),
                   новый, "--add", "--operator", OPERATOR])
    assert rc == 0

    # --- панель ---
    config_web, db_web = _mkconfig(tmp_path, "addweb")
    deps_w, _cid_w = _seed(config_web, db_web)
    deps_w.auth.create_user(username=OPERATOR, password="password123",
                            role="owner")
    client = TestClient(make_app(deps_w))
    token = client.post("/auth/login", json={
        "username": OPERATOR, "password": "password123"}).json()["token"]
    hdr = {"Authorization": f"Bearer {token}"}
    rid_web = {r["email"]: r["id"] for r in
               client.get("/confirm/queue", headers=hdr).json()["pending"]}[
        "lead1@zavod.ru"]
    resp = client.post(f"/confirm/{rid_web}/recipient/add", headers=hdr,
                       json={"email": новый})
    assert resp.status_code == 200, resp.text
    deps_w.store.close()

    st_cli = _added_contact_state(db_cli, новый)
    st_web = _added_contact_state(db_web, новый)
    assert json.dumps(st_cli, ensure_ascii=False, sort_keys=True) == \
        json.dumps(st_web, ensure_ascii=False, sort_keys=True)
    # и это не «пусто == пусто»
    assert st_cli["contact"]["inn"] == "4201000625"
    assert st_cli["contact"]["source"] == "panel_manual"
    assert новый in [r["email"] for r in st_cli["reviews"]]
