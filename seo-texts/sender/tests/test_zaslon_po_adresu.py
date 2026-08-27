# -*- coding: utf-8 -*-
"""Заслон повторного контакта: окно на АДРЕС, потолок на КОМПАНИЮ.

Владелец 27.08: «может переделать ограничение в 90 дней на контакт, а не
инн». До правки last_contact сверялся по email ИЛИ ИНН, поэтому одно письмо
в компанию закрывало ей все адреса на 90 дней — второе письмо коллеге на том
же домене в очередь не попадало (1123 из 1125 отобранных). Снимать защиту с
компании целиком нельзя, иначе десять адресов = десять писем за квартал.
"""
from datetime import datetime, timedelta, timezone

from test_confirm import make_confirm            # noqa: F401 - общие фикстуры
from test_confirm import store, suppression      # noqa: F401

UTC = timezone.utc
ИНН = "4201000625"


def _отправлено(store, email, inn=ИНН, дней=10):
    store.send_log_add(email=email, inn=inn, outcome="sent",
                       ts=datetime.now(UTC) - timedelta(days=дней))


def test_vtoroy_adres_toy_zhe_kompanii_prohodit(store, suppression):
    """Главное: письмо коллеге на том же домене больше не режется по ИНН."""
    _отправлено(store, "info@zavod.ru")
    cs = make_confirm(store, suppression)
    r = cs.submit(email="zakupki@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "pending", r.reason


def test_tot_zhe_adres_v_okne_po_prezhnemu_rezhetsya(store, suppression):
    _отправлено(store, "info@zavod.ru")
    cs = make_confirm(store, suppression)
    r = cs.submit(email="info@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "skipped"
    assert "recent_contact<90d" in r.reason


def test_tot_zhe_adres_starshe_okna_prohodit(store, suppression):
    _отправлено(store, "info@zavod.ru", дней=120)
    cs = make_confirm(store, suppression)
    r = cs.submit(email="info@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "pending", r.reason


def test_tretiy_adres_upiraetsya_v_potolok_kompanii(store, suppression):
    """Два разных адреса в окне — потолок выбран, третий не проходит."""
    _отправлено(store, "info@zavod.ru", дней=20)
    _отправлено(store, "zakupki@zavod.ru", дней=10)
    cs = make_confirm(store, suppression)
    r = cs.submit(email="director@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "skipped"
    assert "company_quota>=2/90d" in r.reason


def test_potolok_schitaet_adresa_a_ne_pisma(store, suppression):
    """Пять повторов на один info@ — один потревоженный человек, не пять."""
    for д in (10, 20, 30, 40, 50):
        _отправлено(store, "info@zavod.ru", дней=д)
    cs = make_confirm(store, suppression)
    r = cs.submit(email="zakupki@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "pending", r.reason


def test_starye_kontakty_ne_zanimayut_potolok(store, suppression):
    """Адреса старше окна в потолок не считаются."""
    _отправлено(store, "info@zavod.ru", дней=200)
    _отправлено(store, "zakupki@zavod.ru", дней=150)
    cs = make_confirm(store, suppression)
    r = cs.submit(email="director@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "pending", r.reason


def test_chuzhaya_kompaniya_potolok_ne_tratit(store, suppression):
    """Письма другому ИНН на потолок этой компании не влияют."""
    _отправлено(store, "a@drugoy.ru", inn="7707083893")
    _отправлено(store, "b@drugoy.ru", inn="7707083893")
    _отправлено(store, "info@zavod.ru")
    cs = make_confirm(store, suppression)
    r = cs.submit(email="zakupki@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "pending", r.reason


def test_bez_inn_potolok_ne_primenyaetsya(store, suppression):
    """ИНН неизвестен — считать компанию нечем, остаётся заслон по адресу."""
    _отправлено(store, "info@zavod.ru", inn=None)
    _отправлено(store, "zakupki@zavod.ru", inn=None)
    cs = make_confirm(store, suppression)
    r = cs.submit(email="director@zavod.ru", subject="Т", body="Б", inn=None)
    assert r.status == "pending", r.reason


def test_neotpravlennye_v_potolok_ne_idut(store, suppression):
    """В потолок считаем только outcome='sent', а не отскоки и пропуски."""
    store.send_log_add(email="info@zavod.ru", inn=ИНН, outcome="bounced",
                       ts=datetime.now(UTC) - timedelta(days=10))
    store.send_log_add(email="sales@zavod.ru", inn=ИНН, outcome="skipped",
                       ts=datetime.now(UTC) - timedelta(days=10))
    _отправлено(store, "zakupki@zavod.ru")
    cs = make_confirm(store, suppression)
    r = cs.submit(email="director@zavod.ru", subject="Т", body="Б", inn=ИНН)
    assert r.status == "pending", r.reason
