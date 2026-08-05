"""Ручное добавление контакта в карточке подтверждения (PLAN-DOBAVIT-ADRES).

Проверяем ровно то, ради чего фича делалась, и ровно то, что она НЕ должна
сломать:
  * новый контакт заводится в базе получателей ПОД ИНН КАРТОЧКИ и сразу
    становится адресатом письма;
  * адрес чужой компании, адрес из стоп-листа, мусорный адрес и карточка не в
    статусе pending — отказ, база при этом не меняется;
  * старая ручка (POST /confirm/{rid}/recipient) остаётся закрытой allow-листом
    контактов — решение владельца «оператор не вписывает произвольный адрес»;
  * отписка закрывает ФАКТИЧЕСКИЙ адрес доставки, а не только строку получателя
    (ФЗ-38): иначе человеку, которому адрес вписали руками, можно писать снова.
"""
import os
import sys
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.api.app import build_deps, make_app  # noqa: E402
from sender.config import Config  # noqa: E402
from sender.confirm import ConfirmBlockedError, ManualRecipientDisabled  # noqa: E402
from sender.dtos import CampaignIn, MessageIn, RecipientIn, SequenceStepIn  # noqa: E402
from sender.errors import ValidationError  # noqa: E402
from sender.store import Store  # noqa: E402
from sender.tests.test_config import BASE_YAML  # noqa: E402

UTC = timezone.utc
INN = "7725104641"
CHUZHOY_INN = "5024002119"


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
    # confirm.mode=all — как в соседних тестах панели
    deps.confirm._config = type("Cfg", (), {
        "get": lambda self, k, d=None: "all" if k == "confirm.mode" else
        deps.config.get(k, d)})()
    return TestClient(make_app(deps)), store, deps


def _hdr(c):
    r = c.post("/auth/login",
               json={"username": "owner", "password": "ownerpass"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _submit(deps, store, *, emails=("office@zavod.ru",), inn=INN):
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    panel = {"emails": [{"email": e, "role": "", "mx_ok": True} for e in emails],
             "company": {"name": "АО «Завод»", "okved": "28.13"}}
    r = deps.confirm.submit(
        email=emails[0], inn=inn, campaign_id=cid,
        subject="s", body="b", panel=panel)
    return cid, r.review_id


# ---------- добавление контакта ----------

def test_add_recipient_creates_and_selects(client):
    c, store, deps = client
    _cid, rid = _submit(deps, store)
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "Snab@Zavod.RU", "note": "с сайта компании"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_recipient"] is True
    assert body["review"]["email"] == "snab@zavod.ru"

    # строка в базе получателей — под ИНН карточки и с меткой источника
    row = store.find_recipient_by_email("snab@zavod.ru")
    assert row is not None
    assert row["inn"] == INN and row["source"] == "panel_manual"
    assert row["company_name"] == "АО «Завод»"   # реквизиты подтянуты

    # адрес попал в контакты карточки — виден в выпадающем списке «кому»
    panel = store.confirm_get(rid)["panel"]
    added = [e for e in panel["emails"] if e["email"] == "snab@zavod.ru"]
    assert len(added) == 1 and added[0]["source"] == "оператор"

    # след в аудите: и заведение контакта, и смена адреса
    actions = [a["action"] for a in store.list_audit(limit=50)]
    assert "recipient_added" in actions and "recipient_changed" in actions


def test_add_recipient_repeat_does_not_duplicate(client):
    c, store, deps = client
    _cid, rid = _submit(deps, store)
    h = _hdr(c)
    first = c.post(f"/confirm/{rid}/recipient/add", headers=h,
                   json={"email": "snab@zavod.ru"})
    assert first.json()["created_recipient"] is True
    second = c.post(f"/confirm/{rid}/recipient/add", headers=h,
                    json={"email": "snab@zavod.ru"})
    assert second.status_code == 200, second.text
    assert second.json()["created_recipient"] is False
    # контакт в карточке не задвоился
    panel = store.confirm_get(rid)["panel"]
    assert [e["email"] for e in panel["emails"]].count("snab@zavod.ru") == 1


def test_add_recipient_rejects_other_company(client):
    """Адрес, уже закреплённый за другим ИНН: upsert_recipient пошёл бы
    ON CONFLICT DO UPDATE и молча переписал бы чужую привязку."""
    c, store, deps = client
    store.upsert_recipient(RecipientIn(
        email="dir@sosed.ru", domain="sosed.ru", inn=CHUZHOY_INN,
        company_name="ООО «Сосед»"))
    _cid, rid = _submit(deps, store)
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "dir@sosed.ru"})
    assert r.status_code == 409, r.text
    assert CHUZHOY_INN in r.json()["detail"]
    # чужая привязка на месте, адрес карточки не тронут
    assert store.find_recipient_by_email("dir@sosed.ru")["inn"] == CHUZHOY_INN
    assert store.confirm_get(rid)["email"] == "office@zavod.ru"


def test_add_recipient_rejects_suppressed(client):
    c, store, deps = client
    deps.suppression.add_email("stop@zavod.ru", "unsubscribe", source="тест")
    _cid, rid = _submit(deps, store)
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "stop@zavod.ru"})
    assert r.status_code == 409, r.text
    assert "стоп-лист" in r.json()["detail"]
    assert store.find_recipient_by_email("stop@zavod.ru") is None


def test_add_recipient_rejects_garbage(client):
    c, store, deps = client
    _cid, rid = _submit(deps, store)
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "abc"})
    assert r.status_code == 400, r.text


def test_add_recipient_rejects_decided_card(client):
    c, store, deps = client
    _cid, rid = _submit(deps, store)
    store.confirm_decide(rid, status="skipped", reason="не тот",
                         decided_by="оператор")
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "snab@zavod.ru"})
    assert r.status_code == 400, r.text
    # база получателей не тронута: проверка идёт ДО записи
    assert store.find_recipient_by_email("snab@zavod.ru") is None


def test_add_recipient_requires_inn(client):
    """Объём, согласованный владельцем, — привязка к ИНН базы обзвона.
    Без ИНН привязывать не к чему и проверка «чужая компания» не работает."""
    c, store, deps = client
    _cid, rid = _submit(deps, store, inn=None)
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "snab@zavod.ru"})
    assert r.status_code == 400, r.text
    assert "ИНН" in r.json()["detail"]


def test_add_recipient_flag_off(client):
    """Мгновенный откат без выкатки: тумблер → 403, старое поведение целиком."""
    c, store, deps = client
    store.set_setting("allow_manual_recipient", False)
    _cid, rid = _submit(deps, store)
    r = c.post(f"/confirm/{rid}/recipient/add", headers=_hdr(c),
               json={"email": "snab@zavod.ru"})
    assert r.status_code == 403, r.text
    with pytest.raises(ManualRecipientDisabled):
        deps.confirm.add_recipient_email(rid, "snab@zavod.ru")


def test_add_recipient_needs_auth(client):
    c, store, deps = client
    _cid, rid = _submit(deps, store)
    r = c.post(f"/confirm/{rid}/recipient/add", json={"email": "snab@zavod.ru"})
    assert r.status_code == 401


def test_old_handle_stays_closed(client):
    """Новая ручка НЕ ослабляет старую: произвольный адрес через
    POST /confirm/{rid}/recipient по-прежнему отбивается, и добавление в одну
    карточку не открывает этот адрес в другой."""
    c, store, deps = client
    h = _hdr(c)
    _cid, rid1 = _submit(deps, store)
    c.post(f"/confirm/{rid1}/recipient/add", headers=h,
           json={"email": "snab@zavod.ru"})
    _cid2, rid2 = _submit(deps, store, emails=("other@zavod.ru",))
    r = c.post(f"/confirm/{rid2}/recipient", headers=h,
               json={"email": "snab@zavod.ru"})
    assert r.status_code == 400, r.text
    with pytest.raises(ConfirmBlockedError):
        deps.confirm.set_recipient_email(rid2, "kto-ugodno@chuzhoy.ru")


def test_add_recipient_queue_clash(client):
    """Дедуп очереди остаётся за штатной ручкой: тот же ИНН+кампания+адрес
    во второй карточке — ValidationError (400), а не молчаливая подмена."""
    c, store, deps = client
    cid, rid1 = _submit(deps, store)
    r2 = deps.confirm.submit(email="snab@zavod.ru", inn=INN, campaign_id=cid,
                             subject="s", body="b",
                             panel={"emails": [{"email": "snab@zavod.ru"}]})
    assert r2.review_id != rid1
    r = c.post(f"/confirm/{rid1}/recipient/add", headers=_hdr(c),
               json={"email": "snab@zavod.ru"})
    assert r.status_code == 400, r.text
    assert "очереди" in r.json()["detail"]


# ---------- ФЗ-38: отписка закрывает адрес доставки ----------

def _sent_to(store, *, recipient_id, campaign_id, delivered_to, step_index=1):
    """Письмо, ушедшее на ПОДМЕНЁННЫЙ оператором адрес (как это делает
    sender.send с to_email): в send_log попадает адрес доставки."""
    step = store.add_step(SequenceStepIn(
        campaign_id=campaign_id, step_index=step_index, delay_hours=0,
        subject_tmpl="s", body_tmpl="b"))
    mid, _ = store.enqueue_message(MessageIn(
        idempotency_key=f"k-{delivered_to}", campaign_id=campaign_id,
        recipient_id=recipient_id, sequence_step_id=step,
        scheduled_at=datetime.now(UTC)))
    store.send_log_add(email=delivered_to, inn=INN, campaign_id=campaign_id,
                       ts=datetime.now(UTC), message_id=mid, outcome="sent")
    return mid


def test_delivery_emails_for_recipient(client):
    c, store, deps = client
    rid_rec = store.upsert_recipient(RecipientIn(
        email="office@zavod.ru", domain="zavod.ru", inn=INN))
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    _sent_to(store, recipient_id=rid_rec, campaign_id=cid,
             delivered_to="snab@zavod.ru")
    _sent_to(store, recipient_id=rid_rec, campaign_id=cid, step_index=2,
             delivered_to="office@zavod.ru")   # базовый — в выдачу не идёт
    assert store.delivery_emails_for_recipient(rid_rec) == ["snab@zavod.ru"]


def test_unsub_closes_delivery_address(client):
    """Человек, которому адрес вписали руками, жмёт «отписаться»: в стоп-лист
    обязан уйти ЕГО адрес, а не только строка получателя из базы."""
    c, store, deps = client
    from sender.unsub import Unsub
    rid_rec = store.upsert_recipient(RecipientIn(
        email="office@zavod.ru", domain="zavod.ru", inn=INN))
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    _sent_to(store, recipient_id=rid_rec, campaign_id=cid,
             delivered_to="snab@zavod.ru")

    unsub = Unsub(deps.config, store, deps.suppression)
    res = unsub.handle_one_click(unsub.make_token(rid_rec, cid))
    assert res.ok is True

    from types import SimpleNamespace
    for addr in ("office@zavod.ru", "snab@zavod.ru"):
        hit = deps.suppression.is_suppressed(
            SimpleNamespace(email=addr, domain="zavod.ru", inn=None))
        assert hit is not None and hit.reason == "unsubscribe", addr


def test_delivery_aliases_noop_without_substitution(client):
    """Подмены не было — ничего лишнего в стоп-лист не уезжает."""
    c, store, deps = client
    rid_rec = store.upsert_recipient(RecipientIn(
        email="office@zavod.ru", domain="zavod.ru", inn=INN))
    cid = store.create_campaign(CampaignIn(
        name="c", legal_entity="ООО «Руспром»", legal_inn="2221239841"))
    _sent_to(store, recipient_id=rid_rec, campaign_id=cid,
             delivered_to="office@zavod.ru")
    recipient = store.get_recipient(rid_rec)
    assert deps.suppression.add_delivery_aliases(
        recipient, "unsubscribe", source="тест") == []
