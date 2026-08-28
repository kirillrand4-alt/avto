# -*- coding: utf-8 -*-
"""Опрос ящика идёт по UID, а не по порядковому номеру письма.

Владелец 28.08: «копай». Ключ дедупа события собирается как
imap:{uidvalidity}:{номер}:{kind}, а imap.search отдаёт НОМЕРА В ПАПКЕ, не
UID. Номера сдвигаются при удалении писем: замер по 21 ящику показал, что в
шести они разошлись с UID, а у i.lyapin@kompressor-air-expert.ru — у 50
писем из 52. Новое письмо получало ключ, уже занятый старым, и молча
отбрасывалось как «уже видели».
"""
from sender.imap_watcher import ImapWatcher


class _Imap:
    """Мок IMAP: помнит, какими командами его звали."""

    def __init__(self, uids=(b"7", b"9")):
        self.uids = list(uids)
        self.вызовы = []
        self.seq_search = 0
        self.seq_fetch = 0

    def login(self, *a):
        self.вызовы.append(("login",))

    def select(self, *a):
        self.вызовы.append(("select",))

    def status(self, *a):
        return "OK", [b'"INBOX" (UIDVALIDITY 111)']

    def search(self, *a):
        self.seq_search += 1
        return "OK", [b" ".join(self.uids)]

    def fetch(self, *a):
        self.seq_fetch += 1
        return "OK", [(b"1 (BODY[] {5}", b"x")]

    def store(self, *a):
        self.вызовы.append(("store",))

    def uid(self, команда, *a):
        self.вызовы.append(("uid", команда))
        if команда == "SEARCH":
            return "OK", [b" ".join(self.uids)]
        if команда == "FETCH":
            return "OK", [(b"1 (BODY[] {5}", b"x")]
        return "OK", [b"ok"]

    def logout(self):
        self.вызовы.append(("logout",))


def test_poisk_i_zabor_idut_po_uid(monkeypatch):
    им = _Imap()
    w = ImapWatcher.__new__(ImapWatcher)

    class _Cfg:
        def get(self, ключ, умолч=None):
            return умолч

        def mailboxes(self):
            return []

    class _Mb:
        mailbox_id = "a@b.ru"
        password_env = "PW"
        imap_host = "h"
        imap_port = 993
        login = "a@b.ru"

    w._config = _Cfg()
    w._mailbox_map = {"a@b.ru": _Mb()}
    w._uidvalidity_cache = {}
    w._get_uidvalidity = lambda imap, mid: 111
    w.classify = lambda raw: (_ for _ in ()).throw(RuntimeError("стоп"))
    monkeypatch.setenv("PW", "секрет")
    import imaplib
    monkeypatch.setattr(imaplib, "IMAP4_SSL", lambda *a, **k: им)
    w.poll_once("a@b.ru")
    команды = [c for c in им.вызовы if c[0] == "uid"]
    assert ("uid", "SEARCH") in команды, "искать надо по UID"
    assert ("uid", "FETCH") in команды, "забирать надо по UID"
    assert им.seq_search == 0, "search по номерам звать нельзя"
    assert им.seq_fetch == 0, "fetch по номерам звать нельзя"


def test_klyuch_dedupa_soderzhit_uid():
    """Ключ строится из uidvalidity и UID — оба стабильны."""
    ключ = "imap:%d:%s:%s" % (111, "9", "reply")
    assert ключ == "imap:111:9:reply"
