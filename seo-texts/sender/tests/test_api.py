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
