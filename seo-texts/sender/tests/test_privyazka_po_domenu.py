"""Ответ с другого адреса той же конторы привязывается по домену.

19.08 «Шато де Талю» ответило «в какую стоимость данное оборудование,
возможно ли получить КП» с andryushchenko@chateaudetalu.ru, а писали мы на
sale@chateaudetalu.ru. In-Reply-To человек не сохранил, привязки по адресу
не нашлось — событие легло без получателя, и горячий лид пролежал неделю.
"""

import os
import sys

import pytest

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from sender.imap_watcher import ImapWatcher  # noqa: E402


class ФейкStore:
    def __init__(self, строки):
        self.строки = строки
        self.спрошено = []

    def recipients_by_domain(self, домен):
        self.спрошено.append(домен)
        return [r for r in self.строки
                if str(r["email"]).rsplit("@", 1)[-1] == домен]


def _сторож(строки):
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = ФейкStore(строки)
    return w


ШАТО = [{"id": 4660, "email": "sale@chateaudetalu.ru", "inn": "2308108667"}]


def test_otvet_s_drugogo_yashchika_toy_zhe_kontory():
    w = _сторож(ШАТО)
    assert w._recipient_by_domain("andryushchenko@chateaudetalu.ru") == 4660


def test_publichnyy_pochtovik_ne_privyazyvaem():
    """Домен mail.ru не значит ничего: так 25.08 любое письмо с bk.ru
    засчиталось бы ответом нашего получателя."""
    w = _сторож([{"id": 7, "email": "kto-to@mail.ru", "inn": "1"}])
    assert w._recipient_by_domain("chuzhoy@mail.ru") is None
    assert w._store.спрошено == [], "публичный домен даже не спрашиваем"


def test_dve_kompanii_na_domene_ne_gadaem():
    w = _сторож([{"id": 1, "email": "a@holding.ru", "inn": "111"},
                 {"id": 2, "email": "b@holding.ru", "inn": "222"}])
    assert w._recipient_by_domain("c@holding.ru") is None


def test_dva_yashchika_odnoy_kompanii_privyazyvayutsya():
    w = _сторож([{"id": 1, "email": "a@zavod.ru", "inn": "111"},
                 {"id": 2, "email": "b@zavod.ru", "inn": "111"}])
    assert w._recipient_by_domain("c@zavod.ru") == 1


def test_neizvestnyy_domen_i_krivoy_adres():
    w = _сторож(ШАТО)
    assert w._recipient_by_domain("kto@nezakomyy.ru") is None
    assert w._recipient_by_domain("") is None
    assert w._recipient_by_domain("без-собаки") is None


def test_store_bez_metoda_ne_ronyaet_priyom():
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = object()
    assert w._recipient_by_domain("a@zavod.ru") is None
