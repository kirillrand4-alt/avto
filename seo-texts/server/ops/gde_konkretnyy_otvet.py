# -*- coding: utf-8 -*-
"""Лежит ли КОНКРЕТНЫЙ ответ оператора в «Отправленных» своего ящика.

Счёт по всем ящикам показал 3462 письма в «Отправленных», из них 3419
совпали с нашими Message-ID: почтовик сам кладёт копию письма, отправленного
через его SMTP. Значит прежний вывод «копии нет вовсе» неверен, и искать
надо адресно — по последним ответам оператора.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config              # noqa: E402
from sender.mailbrowser import MailBrowser    # noqa: E402
from sender.v_otpravlennye import dekodirovat  # noqa: E402

c = sqlite3.connect(r"C:\sender\sender.db", timeout=30)
c.row_factory = sqlite3.Row
ответы = c.execute(
    "SELECT ев.id, ев.event_ts, ев.mailbox_id, ев.message_id, r.email "
    "  FROM events ев LEFT JOIN recipients r ON r.id=ев.recipient_id "
    " WHERE ев.event_type='reply_sent' ORDER BY ев.id DESC LIMIT 4").fetchall()
cfg = Config.load(r"C:\sender\sender.yaml")
mb = MailBrowser(cfg)

for о in ответы:
    print("\n=== ОТВЕТ #%s %s ===" % (о["id"], str(о["event_ts"])[:19]))
    print("   ящик: %s  кому: %s" % (о["mailbox_id"], о["email"]))
    стр = c.execute("SELECT rfc_message_id, subject, sent_at FROM messages "
                    " WHERE id=?", (о["message_id"],)).fetchone() \
        if о["message_id"] else None
    mid = (стр["rfc_message_id"] if стр else "") or ""
    print("   в базе: тема «%s», Message-ID %s"
          % (str(стр["subject"])[:48] if стр else "строки нет", mid[:60]))
    папки = mb.folders(о["mailbox_id"])
    имя = None
    for п in папки:
        н = п if isinstance(п, str) else (п.get("name") or "")
        if "sent" in н.lower() or "отправлен" in dekodirovat(н).lower():
            имя = н
            break
    if not имя:
        print("   папка «Отправленные» не найдена")
        continue
    # Ищем АДРЕСНО: последние письма папки — это свежая рассылка, а ответ
    # оператора старше их всех и в хвост выборки не попадает.
    r = mb.messages(о["mailbox_id"], folder=имя, limit=20,
                    search=str(о["email"] or ""))
    письма = r.get("messages") or []
    print("   в «Отправленных» писем этому адресу: %d" % (r.get("total") or 0))
    нашлось = False
    for п in письма[:8]:
        свой = str(п.get("message_id") or "").strip("<> ")
        метка = "  <-- ЭТОТ" if mid and свой == mid.strip("<> ") else ""
        if метка:
            нашлось = True
        print("      %-24s %-40s %s%s"
              % (str(п.get("date"))[:24], str(п.get("to") or п.get("from"))[:40],
                 str(п.get("subject"))[:36], метка))
    print("   вывод: %s" % ("ответ ЛЕЖИТ в отправленных" if нашлось
                            else "среди последних не видно"))
