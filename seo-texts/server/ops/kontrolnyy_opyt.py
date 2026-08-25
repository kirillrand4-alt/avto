# -*- coding: utf-8 -*-
"""Контрольный опыт: тем же поиском ищем ОБЫЧНОЕ письмо рассылки.

Если письмо рассылки по Message-ID находится, а ответ оператора нет —
разница настоящая, а не кривой поиск. Без этой проверки вывод «ответов в
ящике нет» стоит ровно ничего.
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

for ящик in ("v.melnikov@kompressor-air-expert.ru", "a.balakirev@compressor-store.ru"):
    mb = ящики[ящик]
    рассылка = c.execute(
        "SELECT rfc_message_id, subject, sent_at FROM messages "
        " WHERE mailbox_id=? AND status='sent' AND rfc_message_id IS NOT NULL "
        "   AND COALESCE(subject,'') NOT LIKE 'Re:%' "
        " ORDER BY sent_at DESC LIMIT 1", (ящик,)).fetchone()
    ответ = c.execute(
        "SELECT m.rfc_message_id, m.subject, m.sent_at FROM messages m "
        "  JOIN events ев ON ев.message_id=m.id AND ев.event_type='reply_sent' "
        " WHERE m.mailbox_id=? ORDER BY m.sent_at DESC LIMIT 1", (ящик,)).fetchone()
    print("\n=== %s ===" % ящик)
    imap = imaplib.IMAP4_SSL(mb.imap_host, mb.imap_port, timeout=25)
    imap.login(mb.login, os.getenv(mb.password_env, ""))
    папка = nayti_papku(imap)
    тип, _ = imap.select(папка, readonly=True)
    print("   папка %s: select %s" % (папка, тип))
    for метка, р in (("письмо рассылки", рассылка), ("ответ оператора", ответ)):
        if not р:
            print("   %-18s: нечего искать" % метка)
            continue
        mid = str(р["rfc_message_id"]).strip()
        if not mid.startswith("<"):
            mid = "<%s>" % mid
        т, д = imap.search(None, "HEADER", "Message-ID", mid)
        н = len((д[0] or b"").split()) if т == "OK" else -1
        print("   %-18s: %s | %s | %s"
              % (метка, "НАЙДЕНО" if н > 0 else ("нет" if н == 0 else "поиск %s" % т),
                 str(р["sent_at"])[:19], str(р["subject"])[:40]))
    imap.logout()
