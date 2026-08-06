"""Тесты FastAPI-транспорта (BUILD-NEW) через TestClient: auth-гейт, lead-desk
эндпоинты (взятие/статус/конфликт), UI-ONLY обёртки, роли.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from sender.store import Store, RecipientIn, CampaignIn  # noqa: E402
from sender.leaddesk import LeadDesk  # noqa: E402
from sender.api.app import make_app, build_deps  # noqa: E402


@pytest.fixture
def client(tmp_path):
    # реальный Config из боевого YAML (Gates/Sender требуют его методы)
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    from sender.tests.test_config import BASE_YAML
    from sender.config import Config
    (tmp_path / "c.yaml").write_text(
        BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "api.db")), encoding="utf-8")
    config = Config.load(tmp_path / "c.yaml")
    store = Store(str(tmp_path / "api.db"))
    store.init_schema()
    deps = build_deps(config, store)
    # owner + manager
    deps.auth.create_user(username="owner", password="ownerpass", role="owner")
    deps.auth.create_user(username="mgr", password="mgrpass", role="manager")
    app = make_app(deps)
    return TestClient(app), store, deps


def _token(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---- auth ----

def test_login_and_me(client):
    c, _, _ = client
    tok = _token(c, "owner", "ownerpass")
    r = c.get("/me", headers=_hdr(tok))
    assert r.status_code == 200 and r.json()["role"] == "owner"


def test_login_bad_password(client):
    c, _, _ = client
    r = c.post("/auth/login", json={"username": "owner", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_rejected(client):
    c, _, _ = client
    assert c.get("/leads").status_code == 401
    assert c.get("/me").status_code == 401
    assert c.get("/leads", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_logout(client):
    c, _, _ = client
    tok = _token(c, "owner", "ownerpass")
    assert c.post("/auth/logout", headers=_hdr(tok)).status_code == 200
    assert c.get("/me", headers=_hdr(tok)).status_code == 401  # сессия отозвана


def test_health_no_auth(client):
    c, _, _ = client
    assert c.get("/health").json() == {"status": "ok"}


# ---- lead-desk ----

def _make_lead(store, deps):
    rid = store.upsert_recipient(RecipientIn(email="lead@x.ru", domain="x.ru",
                                             company_name="Альфа"))
    rec = SimpleNamespace(id=rid, email="lead@x.ru", company_name="Альфа", inn=None)
    return deps.leaddesk.push_warm_lead(rec, "t1", "[hot, тел +79001234567] нужен компрессор")


def test_list_and_get_lead(client):
    c, store, deps = client
    lid = _make_lead(store, deps)
    tok = _token(c, "mgr", "mgrpass")
    r = c.get("/leads", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert len(body["leads"]) == 1 and body["leads"][0]["reply_kind"] == "hot"
    assert body["stats"]["total"] == 1
    r2 = c.get(f"/leads/{lid}", headers=_hdr(tok))
    assert r2.json()["lead"]["phone"] == "+79001234567"
    assert [e["action"] for e in r2.json()["history"]] == ["created"]


def test_take_lead_and_conflict(client):
    c, store, deps = client
    lid = _make_lead(store, deps)
    tok_m = _token(c, "mgr", "mgrpass")
    tok_o = _token(c, "owner", "ownerpass")
    r = c.post(f"/leads/{lid}/take", headers=_hdr(tok_m))
    assert r.status_code == 200 and r.json()["lead"]["status"] == "taken"
    # второй менеджер (owner) не может взять уже взятый → 400 (не takeable)
    r2 = c.post(f"/leads/{lid}/take", headers=_hdr(tok_o))
    assert r2.status_code == 400


def test_take_lead_cas_conflict_returns_409(client):
    """Истинная гонка: LeadConflict (CAS-версия сменилась под рукой) → HTTP 409.
    Отличается от 400 «уже takeable»: 409 = конкурентное изменение, фронт гасит
    строку и предлагает обновить."""
    c, store, deps = client
    from sender.leaddesk import LeadConflict
    lid = _make_lead(store, deps)
    tok_m = _token(c, "mgr", "mgrpass")
    orig = deps.leaddesk.take
    deps.leaddesk.take = lambda lead_id, *, user_id: (_ for _ in ()).throw(LeadConflict(lead_id))
    try:
        r = c.post(f"/leads/{lid}/take", headers=_hdr(tok_m))
        assert r.status_code == 409
        assert "taken" in r.json()["detail"].lower() or "conflict" in r.json()["detail"].lower() \
            or "already" in r.json()["detail"].lower()
    finally:
        deps.leaddesk.take = orig


def test_set_status_flow(client):
    c, store, deps = client
    lid = _make_lead(store, deps)
    tok = _token(c, "mgr", "mgrpass")
    c.post(f"/leads/{lid}/take", headers=_hdr(tok))
    r = c.post(f"/leads/{lid}/status", json={"status": "qualified"}, headers=_hdr(tok))
    assert r.status_code == 200 and r.json()["lead"]["status"] == "qualified"
    # нелегальный переход
    r2 = c.post(f"/leads/{lid}/status", json={"status": "new"}, headers=_hdr(tok))
    assert r2.status_code == 400


def test_lead_not_found(client):
    c, _, _ = client
    tok = _token(c, "mgr", "mgrpass")
    assert c.get("/leads/99999", headers=_hdr(tok)).status_code == 404


def test_assign_requires_owner(client):
    c, store, deps = client
    lid = _make_lead(store, deps)
    tok_m = _token(c, "mgr", "mgrpass")
    # manager не может назначать → 403
    r = c.post(f"/leads/{lid}/assign", json={"manager_id": 2}, headers=_hdr(tok_m))
    assert r.status_code == 403
    tok_o = _token(c, "owner", "ownerpass")
    r2 = c.post(f"/leads/{lid}/assign", json={"manager_id": 2}, headers=_hdr(tok_o))
    assert r2.status_code == 200 and r2.json()["lead"]["assigned_to"] == 2


# ---- UI-ONLY обёртки ----

def test_recipients_endpoint(client):
    c, store, deps = client
    r1 = store.upsert_recipient(RecipientIn(email="a@mail.ru", domain="mail.ru"))
    store.set_recipient_validation(r1, valid_status="valid", mx_provider="mailru")
    tok = _token(c, "owner", "ownerpass")
    r = c.get("/recipients", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["count"]["total"] == 1
    # фильтр
    r2 = c.get("/recipients?valid_status=invalid", headers=_hdr(tok))
    assert r2.json()["count"]["total"] == 0


def test_campaigns_events_suppression(client):
    c, store, deps = client
    store.create_campaign(CampaignIn(name="К1", legal_entity="ООО", legal_inn="1"))
    tok = _token(c, "owner", "ownerpass")
    assert len(c.get("/campaigns", headers=_hdr(tok)).json()["campaigns"]) == 1
    assert "events" in c.get("/events", headers=_hdr(tok)).json()
    assert "stats" in c.get("/suppression", headers=_hdr(tok)).json()


def test_analytics_and_gates(client):
    c, _, _ = client
    tok = _token(c, "owner", "ownerpass")
    assert "global" in c.get("/analytics/dashboard", headers=_hdr(tok)).json()
    assert "series" in c.get("/analytics/rates?scope=global&days=3", headers=_hdr(tok)).json()
    assert c.get("/gates/active", headers=_hdr(tok)).json()["trips"] == []
    assert "mailboxes" in c.get("/mailboxes/readiness", headers=_hdr(tok)).json()
    assert "pools" in c.get("/capacity", headers=_hdr(tok)).json()


def test_suppression_remove_owner_only(client):
    c, store, deps = client
    from sender.store import SuppressionIn
    store.suppression_add(SuppressionIn(scope="email", value="x@y.ru", reason="complaint"))
    sid = store.iter_suppression()[0].id
    tok_m = _token(c, "mgr", "mgrpass")
    assert c.delete(f"/suppression/{sid}?reason=test", headers=_hdr(tok_m)).status_code == 403
    tok_o = _token(c, "owner", "ownerpass")
    assert c.delete(f"/suppression/{sid}?reason=test", headers=_hdr(tok_o)).status_code == 200


# ---- Фаза 2.1b: эндпоинты под backlog-экраны ----

def test_campaign_crud_owner(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    # create
    r = c.post("/campaigns", json={"name": "Тест-кампания"}, headers=_hdr(tok_o))
    assert r.status_code == 200
    cid = r.json()["campaign_id"]
    # add step
    rs = c.post(f"/campaigns/{cid}/steps", json={
        "step_index": 0, "subject": "Тема {company_name}", "body": "Привет",
        "delay_hours": 0, "gate": "all"}, headers=_hdr(tok_o))
    assert rs.status_code == 200 and rs.json()["step_id"] > 0
    # detail с воронкой и шагами
    rd = c.get(f"/campaigns/{cid}", headers=_hdr(tok_o))
    assert rd.status_code == 200
    body = rd.json()
    assert body["campaign"]["id"] == cid
    assert len(body["steps"]) == 1 and body["steps"][0]["step_index"] == 0
    assert body["funnel"]["campaign_id"] == cid
    # activate
    ra = c.post(f"/campaigns/{cid}/status", json={"status": "active"}, headers=_hdr(tok_o))
    assert ra.status_code == 200
    assert store.get_campaign(cid).status == "active"
    # аудит записан
    acts = [a["action"] for a in store.list_audit()]
    assert "campaign.create" in acts and "campaign.add_step" in acts and "campaign.status" in acts


def test_campaign_endpoints_forbidden_for_manager(client):
    c, store, deps = client
    tok_m = _token(c, "mgr", "mgrpass")
    assert c.post("/campaigns", json={"name": "x"}, headers=_hdr(tok_m)).status_code == 403
    assert c.get("/campaigns/1", headers=_hdr(tok_m)).status_code == 403


def test_campaign_detail_404(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    assert c.get("/campaigns/99999", headers=_hdr(tok_o)).status_code == 404


def test_users_list_create_deactivate(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    # list (минимум owner+mgr из фикстуры)
    r = c.get("/users", headers=_hdr(tok_o))
    assert r.status_code == 200
    users = r.json()["users"]
    assert any(u["username"] == "owner" for u in users)
    # никаких секретов наружу
    assert all("password_hash" not in u and "totp_secret" not in u for u in users)
    # create manager
    rc = c.post("/users", json={"username": "petrov", "password": "petrovpass1",
                                "role": "manager"}, headers=_hdr(tok_o))
    assert rc.status_code == 200
    uid = rc.json()["user_id"]
    # новый может залогиниться
    assert c.post("/auth/login", json={"username": "petrov", "password": "petrovpass1"}).status_code == 200
    # deactivate → сессии рвутся, логин больше не даёт рабочий доступ
    rd = c.post(f"/users/{uid}/deactivate", headers=_hdr(tok_o))
    assert rd.status_code == 200
    assert store.get_user(uid).is_active is False


def test_users_create_requires_owner(client):
    c, store, deps = client
    tok_m = _token(c, "mgr", "mgrpass")
    assert c.post("/users", json={"username": "x", "password": "y12345678"},
                  headers=_hdr(tok_m)).status_code == 403


def test_settings_owner(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    r = c.get("/settings", headers=_hdr(tok_o))
    assert r.status_code == 200
    assert r.json()["gates"]["domain_bounce_pct"] > 0
    assert "read-only" in r.json()["readonly_note"].lower()


def test_audit_owner_only(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    c.post("/campaigns", json={"name": "audit-check"}, headers=_hdr(tok_o))
    r = c.get("/audit", headers=_hdr(tok_o))
    assert r.status_code == 200
    assert any(a["action"] == "campaign.create" for a in r.json()["audit"])
    # менеджер не видит аудит
    assert c.get("/audit", headers=_hdr(_token(c, "mgr", "mgrpass"))).status_code == 403


def test_domains_summary(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    r = c.get("/domains", headers=_hdr(tok_o))
    assert r.status_code == 200
    doms = r.json()["domains"]
    assert len(doms) > 0
    assert all("domain" in d and "mailboxes" in d and "ready" in d for d in doms)


def test_domain_dns_check(client, monkeypatch):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    from sender.dns import DnsReport
    monkeypatch.setattr(deps.dns, "check", lambda domain: DnsReport(
        domain=domain, spf=True, dkim=True, dmarc=True, mx_ok=True,
        spf_record="v=spf1 ...", dmarc_policy="none", issues=("dmarc_policy_none",)))
    r = c.get("/domains/twin.ru/dns", headers=_hdr(tok_o))
    assert r.status_code == 200
    d = r.json()["dns"]
    assert d["spf"] is True and d["dmarc_policy"] == "none"
    assert "dmarc_policy_none" in d["issues"]


def test_warmup_read(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    r = c.get("/warmup", headers=_hdr(tok_o))
    assert r.status_code == 200
    assert "warmup" in r.json()  # список (пуст, если прогрев не активирован)


def test_compliance_and_subject(client):
    c, store, deps = client
    tok_o = _token(c, "owner", "ownerpass")
    # запись согласия для субъекта
    store.log_consent(email="lead@x.ru", action="send", basis="direct_b2b_offer")
    r = c.get("/compliance", headers=_hdr(tok_o))
    assert r.status_code == 200 and "suppression" in r.json()
    rs = c.get("/subject/lead@x.ru", headers=_hdr(tok_o))
    assert rs.status_code == 200
    assert len(rs.json()["consent_history"]) >= 1
    # просмотр субъекта аудируется
    assert any(a["action"] == "subject.view" for a in store.list_audit())


def test_profile_password_change(client):
    c, store, deps = client
    tok_m = _token(c, "mgr", "mgrpass")
    # неверный старый → 400
    assert c.post("/profile/password", json={"old_password": "wrong",
                  "new_password": "newpass12"}, headers=_hdr(tok_m)).status_code == 400
    # верный старый → успех, старая сессия инвалидируется
    r = c.post("/profile/password", json={"old_password": "mgrpass",
               "new_password": "newpass12"}, headers=_hdr(tok_m))
    assert r.status_code == 200
    # новый пароль работает
    assert c.post("/auth/login", json={"username": "mgr", "password": "newpass12"}).status_code == 200


# ---- сайт: make_site_app (API под /api + SPA статикой с fallback) ----

def _write_dist(tmp_path):
    """Минимальный собранный SPA для теста статики."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><title>panel</title><div id=root></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return str(dist)


def test_site_app_serves_spa_and_api(client, tmp_path):
    from sender.api.app import make_site_app
    _, _, deps = client
    sc = TestClient(make_site_app(deps, _write_dist(tmp_path)))
    # корневой health (для nginx/systemd)
    assert sc.get("/healthz").json()["status"] == "ok"
    # API живёт под /api и держит auth-гейт сквозь монтирование
    assert sc.get("/api/health").status_code == 200
    assert sc.get("/api/leads").status_code == 401
    tok = sc.post("/api/auth/login",
                  json={"username": "owner", "password": "ownerpass"}).json()["token"]
    assert sc.get("/api/leads", headers=_hdr(tok)).status_code == 200
    # SPA: корень → index.html; ассет отдаётся как есть
    r = sc.get("/")
    assert r.status_code == 200 and "panel" in r.text
    assert sc.get("/assets/app.js").status_code == 200
    # client-side-роут без файла → SPA-fallback index.html, НЕ 404
    r2 = sc.get("/campaigns/5")
    assert r2.status_code == 200 and "root" in r2.text


def test_site_app_missing_dir(client, tmp_path):
    from sender.api.app import make_site_app
    _, _, deps = client
    with pytest.raises(FileNotFoundError):
        make_site_app(deps, str(tmp_path / "nope"))


# ---- массовый запрет по ИНН (владелец 06.08: «идёт сделка») ----

def test_suppression_bulk_inn(client):
    c, store, _ = client
    tok = _token(c, "owner", "ownerpass")
    r = c.post("/suppression/bulk-inn", headers=_hdr(tok), json={
        "text": "7701234567, 502700000011\n123\n7701234567"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["added"] == 2 and d["total_parsed"] == 2
    assert d["invalid"]  # «123» — не ИНН
    # повторная загрузка идемпотентна
    r2 = c.post("/suppression/bulk-inn", headers=_hdr(tok),
                json={"text": "7701234567"})
    assert r2.json()["added"] == 0 and r2.json()["existed"] == 1
    # заслон реально действует: guard очереди видит ИНН
    ent = store.suppression_lookup(email="x@y.ru", domain="y.ru",
                                   inn="7701234567")
    assert ent is not None and ent.reason == "deal_in_progress"
    # менеджеру нельзя (только владелец)
    tok_m = _token(c, "mgr", "mgrpass")
    assert c.post("/suppression/bulk-inn", headers=_hdr(tok_m),
                  json={"text": "7701234567"}).status_code in (401, 403)


# ---- кнопка «в автоотправку» ----

def test_auto_send_toggle(client):
    c, _, _ = client
    tok = _token(c, "owner", "ownerpass")
    r = c.get("/auto-send", headers=_hdr(tok))
    # тестовый конфиг без confirm.live_send → живого сендера нет, цикл спит
    assert r.status_code == 200
    assert r.json() == {**r.json(), "enabled": False, "live": False}
    r = c.post("/auto-send", headers=_hdr(tok), json={"enabled": True})
    assert r.json()["enabled"] is True
    r = c.post("/auto-send", headers=_hdr(tok), json={"enabled": False})
    assert r.json()["enabled"] is False


def test_bulk_to_auto_approves_and_schedules(client):
    c, store, _ = client
    from sender.dtos import CampaignIn, RecipientIn, SequenceStepIn
    rid_rec = store.upsert_recipient(RecipientIn(
        email="z@zavod.ru", domain="zavod.ru", tz="Europe/Moscow"))
    cid = store.create_campaign(CampaignIn(
        name="к", legal_entity="ООО Руспром", legal_inn="1"))
    store.add_step(SequenceStepIn(
        campaign_id=cid, step_index=0, delay_hours=0,
        subject_tmpl="{subject}", body_tmpl="{body}"))
    rid, _ = store.confirm_submit(
        email="z@zavod.ru", subject="Тема", body="Тело",
        campaign_id=cid, recipient_id=rid_rec)
    tok = _token(c, "owner", "ownerpass")
    r = c.post("/confirm/bulk-to-auto", headers=_hdr(tok), json={"count": 10})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["moved"] == 1, d
    row = store.confirm_get(rid)
    assert row["status"] == "approved" and row["message_id"]
    m = store.get_message(row["message_id"])
    # письмо создано, запланировано, текст — из карточки оператора
    assert m.status == "scheduled" and m.subject == "Тема"
    # нажатие кнопки включило автоотправку
    assert bool(store.get_setting("auto_send_enabled")) is True
    # повторное нажатие: очередь пуста, ничего не дублируется
    r2 = c.post("/confirm/bulk-to-auto", headers=_hdr(tok), json={"count": 10})
    assert r2.json()["moved"] == 0
