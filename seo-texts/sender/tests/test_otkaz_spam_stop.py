# -*- coding: utf-8 -*-
"""Отказ почтовика «подозрение на спам» останавливает отправку сразу.

СЛУЧАЙ 21.08.2026. Три мейеровских домена выдали 133 письма за два часа. В
12:00 МСК отказ был один на 114 писем, в 13:00 - двадцать девять на сорок
восемь. Никто не остановился: отказ нигде не считался - ни на экране, ни в
гейте, - и лежал только в messages.last_error. Владелец: «остановка отправки
должна идти же сразу при начале попадания в спам».
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.otkaz_spam import (eto_otkaz_spam, nachalo_sutok,  # noqa: E402
                               porogi)
from sender.sender import Sender  # noqa: E402


class _Ящик:
    def __init__(self, mid, division, provider="yandex"):
        self.mailbox_id, self.division, self.provider = mid, division, provider


class _Конфиг:
    def __init__(self, ящики, настройки=None):
        self._я, self._н = ящики, настройки or {}

    def mailboxes(self):
        return self._я

    def get(self, ключ, по_умолчанию=None):
        return self._н.get(ключ, по_умолчанию)


class _Состояние:
    def __init__(self):
        self.paused = False


class _Стор:
    def __init__(self):
        self.события, self.паузы = [], []
        self._состояния = {}

    def append_event(self, e):
        self.события.append(e)
        return (len(self.события), True)

    def count_events(self, *, event_type, since=None, mailbox_id=None, **_):
        return sum(1 for e in self.события
                   if e.event_type == event_type
                   and (mailbox_id is None or e.mailbox_id == mailbox_id))

    def get_mailbox_state(self, mid):
        return self._состояния.get(mid)

    def set_mailbox_paused(self, mid, paused, reason):
        self.паузы.append((mid, paused, reason))
        с = self._состояния.setdefault(mid, _Состояние())
        с.paused = paused


class _Письмо:
    id, recipient_id, campaign_id = 1, 2, 11


def _отправитель(настройки=None):
    s = Sender.__new__(Sender)
    s.store = _Стор()
    s.config = _Конфиг([_Ящик("a@zernosort.ru", "meyer"),
                        _Ящик("b@optic-sort.ru", "meyer"),
                        _Ящик("c@sort-systems.ru", "meyer"),
                        _Ящик("k@kompressor-expert.ru", "kc")], настройки)
    return s


ОТКАЗ = ("(554, b'5.7.1 Message rejected under suspicion of SPAM; "
         "https://ya.cc/1IrBc 1787309422-LoVOOHKc60U0')")


def test_uznayom_otkaz_i_ne_putaem_s_mertvym_yashchikom():
    assert eto_otkaz_spam(ОТКАЗ)
    assert not eto_otkaz_spam("(550, b'Message was not accepted -- invalid "
                              "mailbox.  Local mailbox x@mail.ru is unavailable')")
    assert not eto_otkaz_spam("smtp; 540 5.7.1 <x@rambler.ru>: recipient "
                              "address rejected: Inactive")
    assert not eto_otkaz_spam("(451, b'4.7.1 try again later')")
    assert not eto_otkaz_spam("")


def test_pervyy_otkaz_pishetsya_no_ne_ostanavlivaet():
    """Один отказ бывает и у здоровой отправки - 18.08 был один на 440."""
    s = _отправитель()
    s._otkaz_spam(_Письмо(), "a@zernosort.ru", ОТКАЗ)
    assert len(s.store.события) == 1
    assert s.store.события[0].event_type == "reject_spam"
    assert s.store.события[0].mailbox_id == "a@zernosort.ru"
    assert s.store.паузы == []


def test_vtoroy_otkaz_stavit_yashchik_na_pauzu():
    s = _отправитель()
    for _ in range(2):
        s._otkaz_spam(_Письмо(), "a@zernosort.ru", ОТКАЗ)
    поставлены = [п for п in s.store.паузы if п[1]]
    assert поставлены, "ящик должен встать на паузу"
    assert поставлены[0][0] == "a@zernosort.ru"
    assert "отказ почтовика" in поставлены[0][2]


def test_pyat_otkazov_gasyat_vsyo_napravlenie_a_ne_odin_yashchik():
    """Домены у направления общие, придушивают их вместе."""
    s = _отправитель()
    for ящик in ("a@zernosort.ru", "b@optic-sort.ru", "c@sort-systems.ru",
                 "b@optic-sort.ru", "c@sort-systems.ru"):
        s._otkaz_spam(_Письмо(), ящик, ОТКАЗ)
    на_паузе = {п[0] for п in s.store.паузы if п[1]}
    assert {"a@zernosort.ru", "b@optic-sort.ru", "c@sort-systems.ru"} <= на_паузе
    assert "k@kompressor-expert.ru" not in на_паузе, "КЦ трогать не за что"


def test_porog_nol_vyklyuchaet_rubezh():
    s = _отправитель({"gates.otkaz_stop_yashchik": 0,
                      "gates.otkaz_stop_napravlenie": 0})
    for _ in range(9):
        s._otkaz_spam(_Письмо(), "a@zernosort.ru", ОТКАЗ)
    assert s.store.паузы == []
    assert len(s.store.события) == 9, "событие пишется всегда"


def test_porogi_iz_konfiga():
    assert porogi(_Конфиг([], {})) == (2, 5)
    assert porogi(_Конфиг([], {"gates.otkaz_stop_yashchik": 1,
                               "gates.otkaz_stop_napravlenie": 3})) == (1, 3)
    assert porogi(_Конфиг([], {"gates.otkaz_stop_yashchik": "мусор"}))[0] == 2


def test_okno_scheta_sutki():
    н = nachalo_sutok(datetime(2026, 8, 21, 13, 40, tzinfo=timezone.utc))
    assert н == datetime(2026, 8, 21, 0, 0, tzinfo=timezone.utc)


def test_pauza_idempotentna():
    s = _отправитель()
    for _ in range(4):
        s._otkaz_spam(_Письмо(), "a@zernosort.ru", ОТКАЗ)
    свои = [п for п in s.store.паузы if п[0] == "a@zernosort.ru" and п[1]]
    assert len(свои) == 1, "повторная пауза уже стоящему ящику не нужна"


def test_stroka_na_dashbord_kogda_yashchik_neizvesten():
    """Отказы без ящика обязаны быть видны: у 59 из 61 ящик не записан.

    Гейт по ящику их не увидит (нечего фильтровать), поэтому общая строка
    «почтовик / вся отправка за сутки» считает по всей отправке.
    """
    from sender.gates import Gates

    class _Стор:
        def count_events(self, *, event_type, since=None, mailbox_id=None, **_):
            if mailbox_id is not None:
                return 0                      # ящик у отказов не записан
            return {"sent": 100, "reject_spam": 30}.get(event_type, 0)

        def iter_recipients(self, **_):
            return iter(())

    class _Цфг:
        min_volume, mailbox_reject_pct = 20, 2.0
        window_days = 14
        # active_trips обходит и остальные гейты - им нужны свои пороги
        global_complaint_pct = 0.3
        domain_bounce_pct = domain_complaint_pct = mailbox_bounce_pct = 2.5
        provider_bounce_pct = 2.5

    class _Конф:
        def gates(self):
            return _Цфг()

        def mailboxes(self):
            return []

    g = Gates(_Конф(), _Стор())
    решение = g.check_otkaz_vsego()
    assert решение.tripped, "30 отказов на 130 попыток обязаны зажечь строку"
    assert решение.scope == "почтовик"
    assert решение.metric == "reject_rate"
    assert round(решение.value) == 23
    assert g.check_mailbox_otkaz("a@zernosort.ru").tripped is False
    assert any(t.scope == "почтовик" for t in g.active_trips())
