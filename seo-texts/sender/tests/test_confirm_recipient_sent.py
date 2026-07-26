"""Фичи панели подтверждения (ТЗ 2026-07-24):
1) смена email отправки на другой контакт компании;
2) бейдж «Отправляли» в списках (батч send_log)."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.api.app import build_deps, make_app  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.errors import ValidationError  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402
from sender.dtos import CampaignIn  # noqa: E402

UTC = timezone.utc


@pytest.fixture
def client(tmp_path):
    os.environ.update({f"BOX{i}_PASSWORD": "p" for i in range(1, 6)})
    os.environ["UNSUB_SIGNING_SECRET"] = "s" * 32
    (tmp_path / "c.yaml").write_text(
        BASE_YAML.replace("/tmp/sender.db", str(tmp_path / "api.db")),
        encoding="utf-8")
    config = Config.load(str(tmp_path / "c.yaml"))
    store = Store(str(tmp_path / "api.db"))
    store.init_schema()
    deps = build_deps(config, store)
    deps.auth.create_user(username="owner", password="ownerpass", role="owner")
    return TestClient(make_app(deps)), store, deps


def _hdr(c):
    r = c.post("/auth/login",
               json={"username": "owner", "password": "ownerpass"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---------- Фича 1: смена email ----------

def _submit(deps, store, *, emails):
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    panel = {"emails": [{"email": e, "role": "", "mx_ok": True} for e in emails]}
    r = deps.confirm.submit(
        email=emails[0], inn="7725104641", campaign_id=cid,
        subject="s", body="b", panel=panel)
    return cid, r.review_id


def test_change_email_to_company_contact(client):
    c, store, deps = client
    # confirm.mode=all
    deps.confirm._config = type("Cfg", (), {
        "get": lambda self, k, d=None: "all" if k == "confirm.mode" else
        deps.config.get(k, d)})()
    _cid, rid = _submit(deps, store,
                        emails=["office@zavod.ru", "director@zavod.ru"])
    h = _hdr(c)
    r = c.post(f"/confirm/{rid}/recipient", headers=h,
               json={"email": "director@zavod.ru"})
    assert r.status_code == 200, r.text
    assert r.json()["review"]["email"] == "director@zavod.ru"
    # dedup пересчитан
    assert store.confirm_get(rid)["dedup_key"].split("|")[1] == "director@zavod.ru"


def test_change_email_rejects_foreign(client):
    c, store, deps = client
    deps.confirm._config = type("Cfg", (), {
        "get": lambda self, k, d=None: "all" if k == "confirm.mode" else
        deps.config.get(k, d)})()
    _cid, rid = _submit(deps, store, emails=["office@zavod.ru"])
    h = _hdr(c)
    r = c.post(f"/confirm/{rid}/recipient", headers=h,
               json={"email": "someone@other.ru"})   # не из контактов
    assert r.status_code == 400


def test_change_email_clash_in_queue(client):
    c, store, deps = client
    deps.confirm._config = type("Cfg", (), {
        "get": lambda self, k, d=None: "all" if k == "confirm.mode" else
        deps.config.get(k, d)})()
    cid, rid1 = _submit(deps, store, emails=["a@zavod.ru", "b@zavod.ru"])
    # вторая карточка той же компании уже на b@
    deps.confirm.submit(email="b@zavod.ru", inn="7725104641", campaign_id=cid,
                        subject="s", body="b",
                        panel={"emails": [{"email": "b@zavod.ru"}]})
    with pytest.raises(ValidationError):
        store.confirm_change_email(rid1, "b@zavod.ru")   # dedup-clash


# ---------- Фича 2: бейдж «Отправляли» ----------

def test_sent_flags_batch(client):
    _c, store, _deps = client
    now = datetime.now(UTC)
    store.send_log_add(email="k@zavod.ru", inn="7725104641",
                       campaign_id=1, ts=now - timedelta(days=10),
                       outcome="sent")
    store.send_log_add(email="k@zavod.ru", inn="7725104641",
                       campaign_id=1, ts=now - timedelta(days=5),
                       outcome="replied")
    store.send_log_add(email="old@zavod.ru", inn="5000000000",
                       campaign_id=1, ts=now - timedelta(days=200),
                       outcome="sent")
    flags = store.sent_flags(inns=["7725104641", "5000000000", "9999999999"],
                             emails=["k@zavod.ru"])
    kc = flags["7725104641"]
    assert kc["ever"] is True and kc["replied"] is True
    assert kc["within_90d"] is True
    old = flags["5000000000"]
    assert old["ever"] is True and old["within_90d"] is False  # >90 дней
    assert "9999999999" not in flags                            # не слали


def test_leads_listing_has_sent_badge(client):
    c, store, deps = client
    # лид с записью в send_log
    from sender.dtos import RecipientIn
    rid = store.upsert_recipient(RecipientIn(
        email="lead@zavod.ru", domain="zavod.ru", inn="7725104641",
        company_name="АО Автобан"))
    rec = store.get_recipient(rid)
    deps.leaddesk.push_warm_lead(rec, "thread-1", "Ответ клиента")
    store.send_log_add(email="lead@zavod.ru", inn="7725104641",
                       campaign_id=1, ts=datetime.now(UTC), outcome="sent")
    h = _hdr(c)
    r = c.get("/leads", headers=h)
    assert r.status_code == 200
    lead = next(l for l in r.json()["leads"] if l["email"] == "lead@zavod.ru")
    assert lead["sent"]["ever"] is True
    assert lead["sent"]["within_90d"] is True
