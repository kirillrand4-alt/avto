# -*- coding: utf-8 -*-
"""Лента событий говорит по-русски и объясняет причину.

Владелец 25.08.2026: «сделай, чтобы человекопонятно было — отбивка, за что
отбивка, письмо отправлено и так далее». Ключи detail взяты из живой базы,
а не придуманы.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.sobytiya_slovami import pochemu, yarlyk  # noqa: E402


def test_tipy_perevedeny():
    assert yarlyk("sent") == "письмо отправлено"
    assert yarlyk("bounce") == "отбивка — письмо не дошло"
    assert yarlyk("reply_auto") == "автоответ клиента"


def test_neznakomyy_kod_ne_pryachem():
    """Выдуманный перевод хуже английского: показываем как есть."""
    assert yarlyk("сovsem_novyy") == "сovsem_novyy"


def test_za_chto_otbivka():
    d = {"dsn": {"diagnostic": "smtp; 550 Message was not accepted -- "
                               "invalid mailbox.", "failed": ["esr@mail.ru"]}}
    assert pochemu("bounce", d) == "esr@mail.ru: такого ящика нет"


def test_otbivka_pereполненный_yashchik():
    d = {"dsn": {"diagnostic": "552 mailbox full", "failed": ["a@b.ru"]}}
    assert "переполнен" in pochemu("bounce", d)


def test_otkaz_po_spamu_nazyvaet_pochtovika():
    д = {"error": "(554, b'5.7.1 Message rejected under suspicion of SPAM; "
                  "https://ya.cc/1IrBc')"}
    assert pochemu("reject_spam", д) == "Яндекс не принял письмо: подозрение на спам"


def test_stop_list_govorit_za_chto():
    д = {"reason": "bounce_hard", "addresses": ["esr@mail.ru"]}
    assert pochemu("suppress", д) == "esr@mail.ru: жёсткая отбивка"


def test_propusk_i_povtor():
    assert pochemu("skip", {"reason": "replied"}) == "клиент уже ответил"
    assert pochemu("retry_scheduled",
                   {"reason": "soft_bounce", "depth": 1}) == "мягкая отбивка, попытка 1"


def test_otvet_pokazyvaet_metku_i_nachalo():
    д = {"reply_kind": "автоответ", "snippet": "Здравствуйте!\nВы обратились…"}
    assert pochemu("reply_auto", д) == "автоответ — Здравствуйте! Вы обратились…"


def test_nash_otvet_otlichaet_ruchnoy():
    assert "руками" in pochemu("reply_sent", {"ruchnoy": True, "tema": "Re: Вопрос"})
    assert "панели" in pochemu("reply_sent", {"tema": "Re: Вопрос"})


def test_obychnaya_otpravka_bez_prichiny():
    """Пустая клетка лучше выдуманной причины."""
    assert pochemu("sent", {}) == ""
    assert pochemu("sent", None) == ""
