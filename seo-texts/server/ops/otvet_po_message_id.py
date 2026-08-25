# -*- coding: utf-8 -*-
"""Ищем ответ оператора в «Отправленных» ПО ЕГО Message-ID, а не по адресу.

Поиск по адресу получателя врал: отвечаем мы на тот адрес, с которого
человек написал, а он часто не совпадает с адресом рассылки. Message-ID —
единственный признак, который у письма один и тот же и у нас, и в ящике.
"""
import imaplib
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.v_otpravlennye import nayti_papku  # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
ящики = {x.mailbox_id: x for x in cfg.mailboxes()}
c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ответы = c.execute(
    "SELECT ев.id, ев.event_ts, ев.mailbox_id, m.rfc_message_id mid, m.subject "
    "  FROM events ев JOIN messages m ON m.id=ев.message_id "
    " WHERE ев.event_type='reply_sent' AND m.rfc_message_id IS NOT NULL "
    " ORDER BY ев.id DESC LIMIT 5").fetchall()
print("ответов оператора с Message-ID: %d\n" % len(ответы))

for о in ответы:
    mb = ящики.get(о["mailbox_id"])
    if mb is None:
        print("   ящика %s нет в конфиге" % о["mailbox_id"])
        continue
    пароль = os.getenv(mb.password_env, "")
    mid = str(о["mid"]).strip()
    if not mid.startswith("<"):
        mid = "<%s>" % mid
    print("=== #%s %s | %s" % (о["id"], str(о["event_ts"])[:19], о["mailbox_id"]))
    print("    тема: %s" % str(о["subject"])[:60])
    print("    Message-ID: %s" % mid)
    try:
        imap = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
        imap.login(mb.login, пароль)
        папка = nayti_papku(imap)
        for где in (папка, "INBOX"):
            if not где:
                continue
            imap.select(где, readonly=True)
            тип, данные = imap.search(None, "HEADER", "Message-ID", mid)
            сколько = len((данные[0] or b"").split()) if тип == "OK" else -1
            имя = где if где == "INBOX" else "Отправленные"
            print("    %-14s: %s" % (имя, "НАЙДЕНО %d" % сколько if сколько > 0
                                     else ("нет" if сколько == 0 else "поиск не удался")))
        imap.logout()
    except Exception as e:  # noqa: BLE001
        print("    IMAP не дался: %s" % str(e)[:70])
