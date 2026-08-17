# -*- coding: utf-8 -*-
"""Имя контакта живёт в карточке, а промпт читал пустую колонку.

Замер 17.08 по 120 последним письмам кампании 10: имя есть в карточке
(panel.contact.person) у 10 писем и НИ У ОДНОГО в колонке
recipients.contact_name - она пуста поголовно. Генератор письма читает
именно колонку, поэтому _request возвращал contact_name=None.

Последствие видно числом: 73 письма прошли ВСЕ заслоны надёжности имени, а
поздоровалась модель в двух. Перед этим я правил формулировку промпта
(«ОБЯЗАТЕЛЬНО поздоровайся по имени» вместо «можно») - правка работала
вхолостую, называть было нечего.

Имя берём из того же контакта карточки, откуда уже берётся роль ящика: по
совпадению адреса. Колонка, если заполнена, остаётся главной.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ai_quota import AiQuota  # noqa: E402


class _R:
    def __init__(self, contact_name=""):
        self.id = 1
        self.inn = "1656037013"
        self.email = "antipovis@fond-service.ru"
        self.company_name = 'ООО "Фонд-Сервис"'
        self.okved = "25.62"
        self.segment = ""
        self.contact_name = contact_name
        self.region = "Татарстан"
        self.extra = {}
        self.activity = ""
        self.okved_all = ""
        self.company_full = ""


КАРТОЧКА = {
    "obzvon": {},
    "enrich": {"company": {"activity": "металлообработка"}},
    "contacts": {"emails": [
        {"email": "info@fond-service.ru", "person": "Дежурный", "role": "общий"},
        {"email": "antipovis@fond-service.ru",
         "person": "Антипов Илья Сергеевич", "role": "снабжение/закупки"},
    ]},
}


def _квота(card=КАРТОЧКА):
    q = AiQuota.__new__(AiQuota)
    q._card_for = lambda inn: card
    q._site_facts = lambda inn: {}
    q._segment_division = lambda: {}
    q._division_kartochki = staticmethod(lambda ecomp, r: "")
    q._izbytochnyy_zahod = lambda cid, **kw: ""
    q._digest_for = lambda r: {}
    q._novost_dlya = lambda r: {}
    # поля, которые _request читает у самого объекта квоты
    q._enrich_db = ""
    q._config = None
    q._store = None
    q._cards = lambda: None
    return q


def _запрос(q, r):
    """_request с заглушками того, что ходит в сеть и в чужие базы."""
    try:
        return q._request(r)
    except Exception as ex:                                    # noqa: BLE001
        raise AssertionError(f"_request упал: {type(ex).__name__} {ex}")


def test_imya_beryotsya_iz_kartochki_kogda_kolonka_pusta():
    q = _квота()
    req = _запрос(q, _R(contact_name=""))
    assert req.get("contact_name") == "Антипов Илья Сергеевич", req.get(
        "contact_name")


def test_kolonka_silnee_kartochki():
    """Заполненная колонка остаётся главной — её ставил человек."""
    q = _квота()
    req = _запрос(q, _R(contact_name="Иванов Иван Иванович"))
    assert req.get("contact_name") == "Иванов Иван Иванович"


def test_beryom_kontakt_svoego_yashchika_a_ne_pervyy():
    """В карточке контактов много; имя относится к ТОМУ адресу, куда пишем."""
    q = _квота()
    req = _запрос(q, _R())
    assert req.get("contact_name") != "Дежурный"
    assert (req.get("extra") or {}).get("role") == "снабжение/закупки"


def test_net_kartochki_ne_padaem():
    q = _квота(card=None)
    req = _запрос(q, _R())
    assert req.get("contact_name") is None


def test_chuzhoy_yashchik_imeni_ne_dayot():
    r = _R()
    r.email = "sales@fond-service.ru"          # такого контакта в карточке нет
    req = _запрос(_квота(), r)
    assert req.get("contact_name") is None


ТЕСТЫ = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    сбои = []
    for т in ТЕСТЫ:
        try:
            т()
            print(f"  ок   {т.__name__}")
        except Exception as ex:                                # noqa: BLE001
            сбои.append(т.__name__)
            print(f"  СБОЙ {т.__name__}: {type(ex).__name__} {str(ex)[:160]}")
    print(f"\n{len(ТЕСТЫ) - len(сбои)} прошло, {len(сбои)} упало")
    sys.exit(1 if сбои else 0)
