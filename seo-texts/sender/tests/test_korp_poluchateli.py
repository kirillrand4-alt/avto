"""Признак «получатель на своём почтовом сервере» живёт отдельно от гейта.

09.08 владелец снял гейт молодых доменов: «галочкой могу определять, когда им
отправлять». Вместе с гейтом чуть не исчезла сама возможность различать таких
получателей: blocked_hidden обнулился, галка перестала фильтровать хоть что-то,
а mx_provider в строке письма не отдавался вовсе. Получилось бы хуже, чем до
снятия, — и заслона нет, и не видно, кому пишешь.

Здесь защищается ровно это: признак есть всегда, счётчик считает всегда, галка
работает и при снятом гейте.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

pytest.importorskip("fastapi")

from sender.store import CampaignIn, RecipientIn  # noqa: E402
from sender.tests.test_api import client  # noqa: E402,F401


def _завести(store, deps, письма):
    cid = store.create_campaign(CampaignIn(name="к", legal_entity="ООО «Руспром»",
                                           legal_inn="2221239841", config={}))
    for почта, mx in письма:
        rid = store.upsert_recipient(RecipientIn(
            email=почта, domain=почта.split("@")[1], inn=None,
            company_name="Т", segment="кц"))
        # mx_provider проставляет валидация, в RecipientIn его нет —
        # для теста пишем прямо, это то же поле, что читает панель.
        store._conn.execute("UPDATE recipients SET mx_provider=? WHERE id=?",
                            (mx, rid))
        store._conn.commit()
        store.confirm_submit(campaign_id=cid, recipient_id=rid, email=почта,
                             subject="тема", body="тело", panel={})
    return cid


def _вход(c):
    o = c.post("/auth/login", json={"username": "owner",
                                        "password": "ownerpass"}).json()
    return {"Authorization": "Bearer " + o["token"]}


ПИСЬМА = [("korp@zavod.ru", "other"), ("neizvestno@x.ru", "unknown"),
          ("chelovek@yandex.ru", "yandex"), ("kto@mail.ru", "mailru")]


def test_priznak_svoego_servera_est_vsegda(client):  # noqa: F811
    c, store, deps = client
    _завести(store, deps, ПИСЬМА)
    д = c.get("/confirm/queue?limit=50", headers=_вход(c)).json()
    по_почте = {r["email"]: r for r in д["pending"]}
    assert по_почте["korp@zavod.ru"]["svoy_server"] is True
    assert по_почте["neizvestno@x.ru"]["svoy_server"] is True
    assert по_почте["chelovek@yandex.ru"]["svoy_server"] is False
    assert по_почте["kto@mail.ru"]["mx_provider"] == "mailru"
    assert д["corp_total"] == 2


def test_galka_pryachet_korporativnyh_i_bez_geyta(client):  # noqa: F811
    """Гейт в тестовом конфиге выключен — галка обязана работать всё равно."""
    c, store, deps = client
    _завести(store, deps, ПИСЬМА)
    ш = _вход(c)
    все = c.get("/confirm/queue?limit=50", headers=ш).json()
    скрыто = c.get("/confirm/queue?limit=50&hide_blocked=true",
                   headers=ш).json()
    адреса = {r["email"] for r in скрыто["pending"]}
    assert len(все["pending"]) == 4
    assert адреса == {"chelovek@yandex.ru", "kto@mail.ru"}
    assert скрыто["blocked_hidden"] == 2


# ---- письмо с нуля и копия на другой адрес ---- #

def test_novoe_pismo_lozhitsya_v_ochered(client):  # noqa: F811
    """«Чтобы работало просто как почта»: ящик, адрес, текст — и в очередь."""
    c, store, deps = client
    ш = _вход(c)
    ответ = c.post("/confirm/novoe", headers=ш, json={
        "email": "snab@novyy-zavod.ru", "subject": "Вопрос по компрессорам",
        "body": "Текст письма, написанный руками."})
    assert ответ.status_code == 200, ответ.text
    о = ответ.json()
    assert о["ok"] and о["id"]
    очередь = c.get("/confirm/queue?limit=50", headers=ш).json()["pending"]
    моё = [r for r in очередь if r["email"] == "snab@novyy-zavod.ru"]
    assert len(моё) == 1
    assert моё[0]["subject"] == "Вопрос по компрессорам"
    assert моё[0]["status"] == "pending"          # отправляет человек, не система
    # строка получателя обязана появиться: иначе письмо не видно под фильтром группы
    assert моё[0]["recipient_id"]


def test_novoe_pismo_trebuet_adres_i_tekst(client):  # noqa: F811
    c, store, deps = client
    ш = _вход(c)
    assert c.post("/confirm/novoe", headers=ш, json={
        "email": "не адрес", "subject": "т", "body": "б"}).status_code == 400
    assert c.post("/confirm/novoe", headers=ш, json={
        "email": "a@b.ru", "subject": "", "body": "б"}).status_code == 400


def test_kopiya_na_drugoy_adres(client):  # noqa: F811
    """Исходное письмо остаётся, копия уходит на указанный адрес."""
    c, store, deps = client
    cid = _завести(store, deps, [("pervyy@zavod.ru", "other")])
    ш = _вход(c)
    очередь = c.get("/confirm/queue?limit=50", headers=ш).json()["pending"]
    ид = очередь[0]["id"]
    о = c.post(f"/confirm/{ид}/kopiya", headers=ш,
               json={"email": "obshchiy@zavod.ru"}).json()
    assert о["ok"]
    стало = c.get("/confirm/queue?limit=50", headers=ш).json()["pending"]
    адреса = {r["email"] for r in стало}
    assert "pervyy@zavod.ru" in адреса and "obshchiy@zavod.ru" in адреса
    копия = [r for r in стало if r["email"] == "obshchiy@zavod.ru"][0]
    assert копия["subject"] == "тема" and копия["body"] == "тело"
