# -*- coding: utf-8 -*-
"""Только чтение: разбор отбивок за сегодня и сравнение с прошлыми днями."""
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

s = sqlite3.connect("file:C:/sender/sender.db?mode=ro", uri=True)
s.row_factory = sqlite3.Row
СЕГ = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")

print("=== ОТБИВКИ ЗА СЕГОДНЯ: ТЕКСТ ОШИБКИ ===")
ряды = list(s.execute("SELECT id, created_at, mailbox_id, detail_json, message_id"
                      " FROM events WHERE event_type='bounce' AND created_at >= ?"
                      " ORDER BY id", (СЕГ,)))
for р in ряды:
    d = str(р["detail_json"] or "")
    # вытащим код и суть
    код = re.search(r"\b([45]\.\d\.\d)\b", d)
    txt = re.sub(r"\s+", " ", d)[:150]
    print("  %s  %-30s код %s"
          % (str(р["created_at"])[11:19], str(р["mailbox_id"] or "-")[:30],
             код.group(1) if код else "?"))
    print("     %s" % txt)

print("\n=== КЛАССИФИКАЦИЯ ===")
кл = Counter()
for р in ряды:
    d = str(р["detail_json"] or "").lower()
    if "5.1.1" in d or "no such user" in d or "user unknown" in d or "does not exist" in d \
            or "mailbox unavailable" in d or "адресат" in d:
        кл["адреса НЕТ (мусор в списке)"] += 1
    elif "spam" in d or "5.7.1" in d or "policy" in d or "blocked" in d or "reject" in d:
        кл["отказ по ПОЛИТИКЕ (ящик жив, завернул фильтр)"] += 1
    elif "quota" in d or "full" in d or "4." in d:
        кл["временное (переполнен/тайм-аут)"] += 1
    else:
        кл["не разобрано"] += 1
for k, v in кл.most_common():
    print("  %-46s %d" % (k, v))

print("\n=== ПО ДНЯМ: ОТПРАВЛЕНО И ОТБИТО ===")
for р in s.execute("SELECT substr(created_at,1,10) д,"
                   " SUM(CASE WHEN event_type='sent' THEN 1 ELSE 0 END) ушло,"
                   " SUM(CASE WHEN event_type='bounce' THEN 1 ELSE 0 END) отб"
                   " FROM events WHERE created_at >= '2026-08-25'"
                   " GROUP BY д ORDER BY д"):
    у, о = р["ушло"] or 0, р["отб"] or 0
    print("  %s  ушло %5d  отбито %4d  %5.1f%%" % (р["д"], у, о, 100.0 * о / max(1, у)))

print("\n=== ИТОГ: ОТБИВКИ СЕГОДНЯ ПО ЯЩИКАМ ===")
for р in s.execute("SELECT mailbox_id, COUNT(*) n FROM events"
                   " WHERE event_type='bounce' AND created_at >= ?"
                   " GROUP BY mailbox_id ORDER BY n DESC", (СЕГ,)):
    у = s.execute("SELECT COUNT(*) n FROM events WHERE event_type='sent'"
                  " AND mailbox_id=? AND created_at >= ?",
                  (р["mailbox_id"], СЕГ)).fetchone()["n"]
    print("  %-38s отбито %2d при %3d отправках" % (str(р["mailbox_id"] or "-")[:38],
                                                    р["n"], у))
