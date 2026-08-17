# -*- coding: utf-8 -*-
"""Ящик обязан совпадать с направлением ПИСЬМА, а не только компании.

17.08 Омскводоканал получил письмо про компрессоры за подписью «Руспром
Мейер»: гейт направлений спрашивал «подходит ли компании направление этого
ящика», у фирмы с меткой kc+meyer ответ «да» для обоих, а подпись строится
по направлению ЯЩИКА (brand_for_division). Ручной экран этого не допускал —
он подбирает ящик по panel.letter_division. Здесь то же поле читается
последним рубежом перед SMTP.
"""
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.sender import Sender                              # noqa: E402


class _Карты:
    """Индекс обзвона: компания разрешена ОБОИМ направлениям."""
    active = True

    def divisions(self, inn):
        return {"kc", "meyer"}

    def division(self, inn):
        return "kc+meyer"


class _Стор:
    def __init__(self, письмо_div=None):
        self._div = письмо_div

    def confirm_review_for_message(self, message_id):
        if self._div is None:
            return None
        return {"panel": {"letter_division": self._div}}


def _отправитель(письмо_div=None):
    s = object.__new__(Sender)
    s._cards = _Карты()
    s.store = _Стор(письмо_div)
    s._mailbox_cfg = lambda mid: types.SimpleNamespace(
        mailbox_id=mid, division=("meyer" if "sort" in mid else "kc"))
    return s


_ПИСЬМО = types.SimpleNamespace(id=1)
_ПОЛУЧАТЕЛЬ = types.SimpleNamespace(inn="7726671234")


class TestYashchikPodPismo:
    def test_kc_pismo_s_meyer_yashchika_blokiruetsya(self):
        s = _отправитель("kc")
        r = s.division_block(_ПОЛУЧАТЕЛЬ, "a.kozlov@zernosort.ru",
                             message=_ПИСЬМО)
        assert r is not None and "letter_vs_mailbox" in r, r
        assert "letter=kc" in r and "mailbox=meyer" in r, r

    def test_meyer_pismo_s_kc_yashchika_blokiruetsya(self):
        s = _отправитель("meyer")
        r = s.division_block(_ПОЛУЧАТЕЛЬ, "o.tseyzer@kompressor-expert.ru",
                             message=_ПИСЬМО)
        assert r is not None and "letter_vs_mailbox" in r, r

    def test_svoyo_napravlenie_prohodit(self):
        s = _отправитель("kc")
        assert s.division_block(_ПОЛУЧАТЕЛЬ, "o.tseyzer@kompressor-expert.ru",
                               message=_ПИСЬМО) is None

    def test_bez_metki_pisma_gejt_ne_strozhe(self):
        # Старое письмо без panel.letter_division: заслон остаётся прежним,
        # иначе вся очередь, легшая до внедрения метки, встанет колом.
        s = _отправитель(None)
        assert s.division_block(_ПОЛУЧАТЕЛЬ, "a.kozlov@zernosort.ru",
                               message=_ПИСЬМО) is None

    def test_bez_message_gejt_ne_strozhe(self):
        s = _отправитель("kc")
        assert s.division_block(_ПОЛУЧАТЕЛЬ,
                                "a.kozlov@zernosort.ru") is None

    @pytest.mark.parametrize("мусор", ["", "  ", "оба", "KC+MEYER", None])
    def test_musor_v_metke_ne_blokiruet(self, мусор):
        s = _отправитель(мусор)
        assert s.division_block(_ПОЛУЧАТЕЛЬ, "a.kozlov@zernosort.ru",
                                message=_ПИСЬМО) is None

    def test_sboy_stora_ne_lomaet_otpravku(self):
        s = _отправитель("kc")

        def _падает(_mid):
            raise RuntimeError("база занята")

        s.store.confirm_review_for_message = _падает
        assert s.division_block(_ПОЛУЧАТЕЛЬ,
                                "o.tseyzer@kompressor-expert.ru",
                                message=_ПИСЬМО) is None
