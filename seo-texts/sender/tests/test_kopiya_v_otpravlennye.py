# -*- coding: utf-8 -*-
"""Копия отправленного письма ложится в «Отправленные» самого ящика.

Владелец 25.08.2026: «когда я пишу ответ, этого ответа нету в ящике».
Замер: у v.melnikov@kompressor-air-expert.ru в «Отправленных» два письма,
а по базе за день с него ушло четырнадцать — SMTP копии не оставляет.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from sender.v_otpravlennye import (dekodirovat, nayti_papku,  # noqa: E402
                                   polozhit)

ЯНДЕКС_ОТПРАВЛЕННЫЕ = "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-"


class _Ящик:
    mailbox_id = "v.melnikov@kompressor-air-expert.ru"
    imap_host, imap_port = "imap.yandex.ru", 993
    login = mailbox_id
    password_env = "TEST_MB_PASS"


class _IMAP:
    def __init__(self, строки, тип_append="OK"):
        self._строки, self._тип = строки, тип_append
        self.положено = []
        self.вышел = False

    def list(self):
        return "OK", self._строки

    def append(self, папка, флаги, когда, письмо):
        self.положено.append((папка, флаги, письмо))
        return self._тип, [b""]

    def logout(self):
        self.вышел = True


def test_imya_papki_iz_utf7():
    assert dekodirovat(ЯНДЕКС_ОТПРАВЛЕННЫЕ) == "Отправленные"
    assert dekodirovat("INBOX") == "INBOX"
    assert dekodirovat("&BBoEPgRABDcEOAQ9BDA-") == "Корзина"


def test_papku_nahodim_po_flagu_a_ne_po_imeni():
    """Имя у почтовика своё; \\Sent — единственный надёжный признак."""
    imap = _IMAP([b'(\\HasNoChildren) "|" "INBOX"',
                  b'(\\HasNoChildren \\Sent) "|" "' + ЯНДЕКС_ОТПРАВЛЕННЫЕ.encode() + b'"',
                  b'(\\HasNoChildren \\Trash) "|" "&BBoEPgRABDcEOAQ9BDA-"'])
    assert nayti_papku(imap) == ЯНДЕКС_ОТПРАВЛЕННЫЕ


def test_bez_flaga_ishchem_po_znakomomu_imeni():
    imap = _IMAP([b'(\\HasNoChildren) "|" "INBOX"',
                  b'(\\HasNoChildren) "|" "' + ЯНДЕКС_ОТПРАВЛЕННЫЕ.encode() + b'"'])
    assert nayti_papku(imap) == ЯНДЕКС_ОТПРАВЛЕННЫЕ


def test_pismo_lozhitsya_prochitannym():
    os.environ["TEST_MB_PASS"] = "секрет"
    imap = _IMAP([b'(\\Sent) "|" "' + ЯНДЕКС_ОТПРАВЛЕННЫЕ.encode() + b'"'])
    assert polozhit(_Ящик(), b"MIME", opener=lambda _mb: imap) is True
    assert imap.положено[0][0] == ЯНДЕКС_ОТПРАВЛЕННЫЕ
    assert imap.положено[0][1] == "\\Seen"
    assert imap.положено[0][2] == b"MIME"
    assert imap.вышел, "соединение обязано закрыться"


def test_sboy_kopii_ne_ronyaet_otpravku():
    """Письмо уже ушло: неудачная копия — неудобство, а не потеря."""
    os.environ["TEST_MB_PASS"] = "секрет"

    class _Злой(_IMAP):
        def append(self, *_a, **_k):
            raise RuntimeError("сервер закрыл соединение")

    злой = _Злой([b'(\\Sent) "|" "' + ЯНДЕКС_ОТПРАВЛЕННЫЕ.encode() + b'"'])
    assert polozhit(_Ящик(), b"MIME", opener=lambda _mb: злой) is False
    assert злой.вышел


def test_bez_parolya_ne_lezem_v_set():
    os.environ.pop("TEST_MB_PASS", None)
    звали = []
    assert polozhit(_Ящик(), b"MIME",
                    opener=lambda _mb: звали.append(1)) is False
    assert not звали, "без пароля соединение открывать незачем"
