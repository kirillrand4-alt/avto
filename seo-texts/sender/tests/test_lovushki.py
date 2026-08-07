"""Заслон от спам-ловушек.

Главное, что здесь защищается, — правило опечаток НЕ трогает живые домены.
Первая редакция сравнивала домены по позициям и объявила ловушками maco.ru
(реальный сайт MACO, оконная фурнитура) и diat.ru. Снятие по такому правилу
уничтожило бы живые контакты — ровно как выброс адресов по коду 550, от
которого спасла проверка ответа сервера. Поэтому список ЖИВЫЕ ниже — не
формальность, а условие, при котором правило вообще допущено к очереди.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sender.lovushki import (ВОСКРЕСШИЙ, ОПЕЧАТКА, СЛУЖЕБНЫЙ,  # noqa: E402
                             ЗаслонЛовушек, вид_ловушки, похоже_на_опечатку,
                             служебный)

# Домены, зарегистрированные под ловлю: один шаг правки от популярного.
# Различие либо в имени (mai, gmial), либо в НЕсуществующей зоне (ur, ry).
ЛОВУШКИ = ["mai.ru", "mial.ru", "maill.ru", "mail.ur", "yandx.ru", "yadnex.ru",
           "yandex.ry", "gmai.com", "gmial.com", "inbox.ry",
           "ramblr.ru", "ranbler.ru", "outlok.com", "hotmial.com"]

# Настоящие домены — ни один не должен быть принят за опечатку.
ЖИВЫЕ = ["maco.ru", "diat.ru", "mail.ru", "yandex.ru", "gmail.com", "list.ru",
         "bk.ru", "inbox.ru", "ya.ru", "rusprom.ru", "prokompressor.ru",
         "meyer-corp.ru", "tmk-group.ru", "sibur.ru", "lukoil.com",
         "magnit.ru", "kamaz.ru", "atlas.ru", "mailru.ru", "mail-ru.ru",
         "nlmk.com", "inbox.lv", "list.am", "yandex.com", "yandex.by",
         "mail.kz", "mail.by", "lider.ru", "liter.ru", "irbis.ru", "orbis.ru",
         "kompas.ru", "kompress.ru", "himmash.ru", "uralmash.ru",
         # Зоны-соседи популярных: настоящие провайдеры, а не опечатки.
         # inbox.eu поймано прогоном по базе 07.08 — правило считало его
         # опечаткой inbox.ru, потому что различие ровно в один знак.
         # gmail.co здесь же: .co — реальная зона Колумбии, и хотя её любят
         # тайпсквоттеры, живой домен в ней дороже пойманной ловушки.
         "inbox.eu", "gmail.co", "mail.com", "locotech.ru", "mail.ua"]


@pytest.mark.parametrize("домен", ЛОВУШКИ)
def test_opechatki_lovyatsya(домен):
    assert похоже_на_опечатку(домен) is not None


@pytest.mark.parametrize("домен", ЖИВЫЕ)
def test_zhivye_domeny_ne_trogaem(домен):
    assert похоже_на_опечатку(домен) is None, "живой домен принят за ловушку"


@pytest.mark.parametrize("адрес,ждём", [
    ("abuse@z.ru", "abuse"),
    ("postmaster@z.ru", "postmaster"),
    ("spam-report@z.ru", "spam"),
    ("no-reply@z.ru", "no-reply"),
    ("trap@z.ru", "trap"),
    # ниже — живые локальные части, похожие на служебные лишь началом
    ("abuseev@z.ru", None),
    ("securitykom@z.ru", None),
    ("rootkin@z.ru", None),
    ("info@z.ru", None),
    ("zakupki@z.ru", None),
])
def test_sluzhebnye(адрес, ждём):
    assert служебный(адрес) == ждём


def test_voskresshiy_tolko_pri_dvuh_usloviyah():
    """Отбивался И принимает сейчас — ловушка. По отдельности — нет."""
    assert вид_ловушки("x@z.ru", отбивался=True, живой_по_пробе=True)[0] == ВОСКРЕСШИЙ
    assert вид_ловушки("x@z.ru", отбивался=True, живой_по_пробе=False) is None
    assert вид_ловушки("x@z.ru", отбивался=False, живой_по_пробе=True) is None


def test_poryadok_pravil():
    """Служебный адрес важнее прочего: он ловушка независимо от домена."""
    вид, _ = вид_ловушки("abuse@mai.ru")
    assert вид == СЛУЖЕБНЫЙ
    вид, _ = вид_ловушки("director@mai.ru")
    assert вид == ОПЕЧАТКА


def test_ne_adres_ne_lovushka():
    assert вид_ловушки("") is None
    assert вид_ловушки("просто-строка") is None


# ---- проход по очереди ---- #

class _Store:
    def __init__(self, отбивались=()):
        self.отбивались = set(отбивались)
        self.решения = []
        self.suppression = []

    def suppression_values(self, *, reason, scope="email"):
        return set(self.отбивались) if reason == "bounce_hard" else set()

    def confirm_decide(self, rid, **kw):
        self.решения.append((rid, kw.get("status"), kw.get("reason")))
        return True

    def suppression_add(self, entry):
        self.suppression.append((entry.scope, entry.value, entry.reason))
        return (1, True)


class _Probe:
    def __init__(self, живые=()):
        self.живые = set(живые)

    def verdict_emails(self, вердикт):
        return set(self.живые)


ОЧЕРЕДЬ = [
    {"id": 1, "email": "director@zavod.ru", "kind": "outbound"},
    {"id": 2, "email": "abuse@zavod.ru", "kind": "outbound"},
    {"id": 3, "email": "snab@mai.ru", "kind": "outbound"},
    {"id": 4, "email": "old@zavod.ru", "kind": "outbound"},
    {"id": 5, "email": "office@maco.ru", "kind": "outbound"},
]


def test_prohod_snimaet_tolko_lovushki():
    store = _Store(отбивались=["old@zavod.ru"])
    заслон = ЗаслонЛовушек(store=store, probe=_Probe(живые=["old@zavod.ru"]))
    итог = заслон.применить(ОЧЕРЕДЬ)
    assert итог["снято"] == 3
    assert sorted(r[0] for r in store.решения) == [2, 3, 4]
    assert итог["ид"] == {2, 3, 4}
    assert итог[СЛУЖЕБНЫЙ] == 1 and итог[ОПЕЧАТКА] == 1 and итог[ВОСКРЕСШИЙ] == 1
    assert all(r[2] == "spam_trap" for r in store.suppression)


def test_otvety_klientov_ne_trogaem():
    письма = [{"id": 7, "email": "abuse@z.ru", "kind": "reply"}]
    store = _Store()
    assert ЗаслонЛовушек(store=store).применить(письма)["снято"] == 0


def test_bez_proby_voskresshih_ne_ishchem():
    """Нет кэша проб — правило молчит, а не считает всех отбившихся ловушками."""
    store = _Store(отбивались=["old@zavod.ru"])
    итог = ЗаслонЛовушек(store=store).применить(ОЧЕРЕДЬ)
    assert итог[ВОСКРЕСШИЙ] == 0 and итог["снято"] == 2
