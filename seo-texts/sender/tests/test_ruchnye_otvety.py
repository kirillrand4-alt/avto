# -*- coding: utf-8 -*-
"""Ручной ответ из веб-почты попадает в диалог компании.

Владелец 25.08.2026 отвечал клиентам прямо из веб-интерфейса почтовика —
для системы таких ответов не существовало вовсе.
"""
import os
import sys
from email.message import EmailMessage

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.ruchnye_otvety import (chey_otvet, razobrat,  # noqa: E402
                                   sobrat)

НАШ_MID = "<178756612239.14928.1@compressor-store.ru>"
РУЧНОЙ_MID = "<ruchnoy-1@mail.yandex.ru>"


def _письмо(mid, komu, tema, telo, in_reply_to=None):
    m = EmailMessage()
    m["Message-ID"] = mid
    m["From"] = "Алексей <a.balakirev@compressor-store.ru>"
    m["To"] = komu
    m["Subject"] = tema
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = in_reply_to
    m.set_content(telo)
    return m.as_bytes()


class _Ящик:
    mailbox_id = "a.balakirev@compressor-store.ru"
    imap_host, imap_port = "imap.mail.ru", 993
    login = mailbox_id
    password_env = "TEST_MB_PASS"


class _IMAP:
    def __init__(self, письма):
        self._письма = письма          # {uid: raw}
        self.выбрана = None
        self.критерий = None

    def list(self):
        return "OK", [b'(\\Sent) "|" "Sent"']

    def select(self, папка, readonly=False):
        self.выбрана = (папка, readonly)
        return "OK", [b"1"]

    def uid(self, команда, *арг):
        if команда == "SEARCH":
            self.критерий = арг[1:]
            return "OK", [b" ".join(str(u).encode() for u in self._письма)]
        if команда == "FETCH":
            uid = int(арг[0])
            return "OK", [(b"1 (RFC822 {})", self._письма[uid])]
        return "NO", []

    def logout(self):
        return "OK", []


class _Стор:
    def __init__(self, по_ветке=None):
        self._по_ветке = по_ветке or {}

    def find_message_by_rfc_id(self, mid):
        return self._по_ветке.get(mid)

    def find_recipient_by_email(self, адрес):
        return {"id": 777} if адрес == "znakomyy@zavod.ru" else None


class _Письмо:
    def __init__(self, rid):
        self.recipient_id = rid


def test_svoyo_pismo_ne_beryom():
    """Панельное письмо в «Отправленных» лежит по праву — оно уже в базе."""
    os.environ["TEST_MB_PASS"] = "секрет"
    imap = _IMAP({10: _письмо(НАШ_MID, "kto@zavod.ru", "Вопрос", "текст")})
    письма, верх = sobrat(_Ящик(), nash_li=lambda m: m == НАШ_MID,
                          opener=lambda _mb: imap)
    assert письма == []
    assert верх == 10
    assert imap.выбрана[1] is True, "папку открываем только на чтение"


def test_ruchnoy_otvet_podbiraem():
    os.environ["TEST_MB_PASS"] = "секрет"
    imap = _IMAP({11: _письмо(РУЧНОЙ_MID, "kto@zavod.ru", "Re: Вопрос",
                              "Добрый день, готовы обсудить", НАШ_MID)})
    письма, верх = sobrat(_Ящик(), nash_li=lambda m: m == НАШ_MID,
                          opener=lambda _mb: imap)
    assert len(письма) == 1
    п = письма[0]
    assert п["rfc_message_id"] == РУЧНОЙ_MID
    assert п["komu"] == "kto@zavod.ru"
    assert "готовы обсудить" in п["telo"]
    assert верх == 11


def test_starye_uid_ne_perechityvaem():
    """«UID n:*» всегда отдаёт хотя бы одно письмо — старое отбрасываем сами."""
    os.environ["TEST_MB_PASS"] = "секрет"
    imap = _IMAP({11: _письмо(РУЧНОЙ_MID, "kto@zavod.ru", "Re:", "текст")})
    письма, верх = sobrat(_Ящик(), nash_li=lambda _m: False, s_uid=11,
                          opener=lambda _mb: imap)
    assert письма == []
    assert верх == 11
    assert imap.критерий[0] == "UID"


def test_poluchatelya_nahodim_po_vetke():
    """Отвечают часто с другого адреса — спасает только In-Reply-To."""
    стор = _Стор({НАШ_MID: _Письмо(42)})
    п = razobrat(_письмо(РУЧНОЙ_MID, "drugoy@zavod.ru", "Re:", "т", НАШ_MID))
    assert chey_otvet(стор, п) == 42


def test_bez_vetki_probuem_adres():
    стор = _Стор()
    п = razobrat(_письмо(РУЧНОЙ_MID, "znakomyy@zavod.ru", "Тема", "т"))
    assert chey_otvet(стор, п) == 777


def test_chuzhoy_adres_bez_vetki_ne_privyazyvaem():
    стор = _Стор()
    п = razobrat(_письмо(РУЧНОЙ_MID, "nikto@nezavod.ru", "Тема", "т"))
    assert chey_otvet(стор, п) is None


def test_bez_parolya_v_set_ne_lezem():
    os.environ.pop("TEST_MB_PASS", None)
    звали = []
    письма, верх = sobrat(_Ящик(), nash_li=lambda _m: False,
                          opener=lambda _mb: звали.append(1))
    assert письма == [] and верх == 0 and not звали
