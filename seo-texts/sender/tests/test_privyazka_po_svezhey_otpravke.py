# -*- coding: utf-8 -*-
"""Домен делят две компании — привязываем по тому, кому писали последними.

Владелец 28.08 показал автоответ «я закончила работу в компании, обращайтесь
к Пушиной Александре» с virtex-food.ru. Там у нас две компании — АО «Виртекс»
и ООО «ВТ Логистик», — и привязка по домену честно отказалась гадать: событие
легло «входящим вне переписки», без получателя и без карточки в ленте.
Гадать и не нужно: письмо ушло на sales-p@ в 03:09, автоответ пришёл в 03:10.
"""
from datetime import datetime, timedelta, timezone

from sender.imap_watcher import ImapWatcher

UTC = timezone.utc


class _Store:
    """Мок: домен virtex-food.ru у двух компаний, отправки заданы явно."""

    def __init__(self, отправки, строки=None):
        self._отправки = отправки
        self._строки = строки if строки is not None else [
            {"id": 6921, "email": "its@virtex-food.ru", "inn": "5407220457"},
            {"id": 18426, "email": "lawyer@virtex-food.ru", "inn": "5445014374"},
            {"id": 30282, "email": "sales-p@virtex-food.ru", "inn": "5445014374"},
        ]

    def recipients_by_domain(self, домен):
        return self._строки if домен == "virtex-food.ru" else []

    def send_log_history(self, *, email=None, inn=None, limit=10):
        ts = self._отправки.get((email or "").lower())
        return [{"ts": ts.isoformat(), "outcome": "sent"}] if ts else []


def _вотчер(store):
    w = ImapWatcher.__new__(ImapWatcher)
    w._store = store
    return w


def test_beryom_tu_komu_pisali_poslednimi():
    сейчас = datetime.now(UTC)
    w = _вотчер(_Store({
        "sales-p@virtex-food.ru": сейчас - timedelta(minutes=1),
        "lawyer@virtex-food.ru": сейчас - timedelta(days=3),
    }))
    assert w._recipient_by_svezhey_otpravkoy("dmg@virtex-food.ru") == 30282


def test_staraya_otpravka_ne_schitaetsya():
    """Писали месяц назад — это уже не ответ на наше письмо."""
    сейчас = datetime.now(UTC)
    w = _вотчер(_Store({"sales-p@virtex-food.ru": сейчас - timedelta(days=40)}))
    assert w._recipient_by_svezhey_otpravkoy("dmg@virtex-food.ru") is None


def test_dvum_pisali_pochti_razom_ne_gadaem():
    сейчас = datetime.now(UTC)
    w = _вотчер(_Store({
        "sales-p@virtex-food.ru": сейчас - timedelta(minutes=1),
        "its@virtex-food.ru": сейчас - timedelta(minutes=3),
    }))
    assert w._recipient_by_svezhey_otpravkoy("dmg@virtex-food.ru") is None


def test_pochtovik_ne_privyazyvaem():
    w = _вотчер(_Store({}))
    assert w._recipient_by_svezhey_otpravkoy("someone@mail.ru") is None


def test_odin_poluchatel_ostavlyaem_prezhney_privyazke():
    """Один адрес на домене — это работа _recipient_by_domain, не наша."""
    сейчас = datetime.now(UTC)
    w = _вотчер(_Store({"its@virtex-food.ru": сейчас},
                       строки=[{"id": 6921, "email": "its@virtex-food.ru",
                                "inn": "5407220457"}]))
    assert w._recipient_by_svezhey_otpravkoy("dmg@virtex-food.ru") is None


def test_bez_otpravok_nichego_ne_vozvrashchaem():
    w = _вотчер(_Store({}))
    assert w._recipient_by_svezhey_otpravkoy("dmg@virtex-food.ru") is None


def test_krivoy_adres_ne_ronyaet():
    w = _вотчер(_Store({}))
    assert w._recipient_by_svezhey_otpravkoy("") is None
    assert w._recipient_by_svezhey_otpravkoy("без-собаки") is None
