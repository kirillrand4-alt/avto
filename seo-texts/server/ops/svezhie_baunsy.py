# -*- coding: utf-8 -*-
"""Свежие баунсы: те, что пришли после разбора первых четырнадцати.

Вопрос один: та же это природа (мусор в базе, приговор ставит сама
отбивка) или новая — например, репутация ящика или домена.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ГРАНИЦА = "2026-08-24T10:31"

строки = c.execute(
    "SELECT e.event_ts, e.mailbox_id, e.message_id, e.detail_json, "
    "       r.email, r.mx_provider, m.sent_at "
    "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
    "  LEFT JOIN messages m ON m.id=e.message_id "
    " WHERE e.event_type='bounce' AND e.event_ts >= ? ORDER BY e.event_ts",
    (ГРАНИЦА,)).fetchall()
print("баунсов после %s: %d\n" % (ГРАНИЦА, len(строки)))

кол = [к[1] for к in c.execute("PRAGMA table_info(addr_probe)")]
итог = Counter()
for р in строки:
    адрес = str(р["email"] or "?")
    п = c.execute("SELECT verdict, source, ts FROM addr_probe WHERE lower(email)=? "
                  "ORDER BY ts LIMIT 1", (адрес.lower(),)).fetchone()
    отпр = str(р["sent_at"] or "")[:16]
    if not п:
        порядок = "пробы не было"
    elif str(п["ts"])[:16] < отпр:
        порядок = "проба ДО отправки: %s [%s]" % (п["verdict"], п["source"] or "-")
    else:
        порядок = "проба после: %s [%s]" % (п["verdict"], п["source"] or "-")
    итог[порядок.split(":")[0]] += 1
    д = str(р["detail_json"] or "")
    и = д.find('"diagnostic')
    текст = д[и:и + 130].replace("\\n", " ") if и >= 0 else ""
    print("  %s %-30s ящик %-30s"
          % (str(р["event_ts"])[:16], адрес[:30],
             str(р["mailbox_id"] or "?")[:30]))
    print("        отправлено %s | %s" % (отпр, порядок))
    if текст:
        print("        %s" % текст[:120])

print("\n=== ИТОГ ПО ПОРЯДКУ ===")
for к, н in итог.most_common():
    print("  %-28s %d" % (к, н))

print("\n=== ПО ЯЩИКАМ-ОТПРАВИТЕЛЯМ (все баунсы за сутки) ===")
for р in c.execute(
        "SELECT e.mailbox_id я, COUNT(*) n FROM events e "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=date('now') "
        " GROUP BY я ORDER BY n DESC LIMIT 10"):
    о = c.execute("SELECT COUNT(*) n FROM messages WHERE mailbox_id=? "
                  "  AND status='sent' AND substr(COALESCE(sent_at,created_at),1,10)"
                  "=date('now')", (р["я"],)).fetchone()["n"]
    print("  %-36s баунсов %3d из %3d отправленных  %5.1f%%"
          % (str(р["я"])[:36], р["n"], о, 100.0 * р["n"] / о if о else 0))
