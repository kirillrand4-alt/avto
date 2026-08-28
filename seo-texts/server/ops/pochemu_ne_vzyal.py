# -*- coding: utf-8 -*-
"""Почему добор не взял три письма: ищем их в ящике по UID."""
import imaplib
import os
import sys
from email import message_from_bytes
from email.header import decode_header, make_header

sys.path.insert(0, r"C:\sender")
from sender.config import Config                                  # noqa: E402
from sender.store import Store                                    # noqa: E402

ИЩЕМ = {"i.lyapin@kompressor-air-trade.ru": ["isaev@findcon.ru",
                                             "aseitov@asiacement.ru"],
        "v.ivanov@optic-sort.ru": ["a.udachin@sodrugestvo.ru",
                                   "postmaster@agrotek.com"]}
cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
карта = {mb.mailbox_id: mb for mb in cfg.mailboxes()}
for ящик, адреса in ИЩЕМ.items():
    mb = карта.get(ящик)
    if not mb:
        print("%s: нет в конфиге" % ящик); continue
    пароль = os.getenv(mb.password_env, "")
    if not пароль:
        print("%s: нет пароля в %s" % (ящик, mb.password_env)); continue
    print("=== %s ===" % ящик)
    try:
        im = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
        im.login(mb.login, пароль)
        im.select("INBOX")
        typ, d = im.status("INBOX", "(UIDVALIDITY)")
        uv = str(d[0]).split("UIDVALIDITY")[-1].strip(" )'\"") if d else "?"
        for а in адреса:
            typ, data = im.uid("SEARCH", None, "FROM", '"%s"' % а)
            uids = (data[0] or b"").split()
            print("   %-28s uid: %s" % (а, [u.decode() for u in uids] or "НЕ НАЙДЕНО"))
            for u in uids[:2]:
                us = u.decode()
                ключ_o = "imap:%s:%s:other" % (uv, us)
                ключ_r = "imap:%s:%s:reply" % (uv, us)
                with store._lock:
                    есть = store._conn.execute(
                        "SELECT id, event_type, dedup_key FROM events "
                        " WHERE dedup_key IN (?,?)", (ключ_o, ключ_r)).fetchall()
                typ2, md = im.uid("FETCH", us, "(FLAGS)")
                флаги = str(md[0]) if md else "?"
                print("      uid %-6s событие: %s | %s"
                      % (us, [dict(x) for x in есть] or "НЕТ", флаги[:70]))
        im.logout()
    except Exception as ex:                                       # noqa: BLE001
        print("   ошибка: %s: %s" % (type(ex).__name__, str(ex)[:100]))
