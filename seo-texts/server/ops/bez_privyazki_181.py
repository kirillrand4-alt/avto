# -*- coding: utf-8 -*-
"""181 входящее без привязки: что это и есть ли среди них живые ответы."""
import json
import re
import sqlite3
from collections import Counter

ПОЧТОВИКИ = {"mail.ru", "yandex.ru", "ya.ru", "gmail.com", "bk.ru", "list.ru",
             "inbox.ru", "rambler.ru", "internet.ru", "outlook.com", "icloud.com"}
c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
строки = c.execute(
    "SELECT id, event_ts, mailbox_id, detail_json FROM events "
    " WHERE recipient_id IS NULL AND event_type IN ('reply','reply_auto','other') "
    " ORDER BY event_ts DESC").fetchall()
print("без привязки всего: %d" % len(строки))

# домены наших получателей — чтобы понять, наш это контакт или посторонний
наши_дом = {(r[0] or "").lower() for r in c.execute(
    "SELECT DISTINCT domain FROM recipients WHERE domain IS NOT NULL")}
вид = Counter()
кандидаты = []
шум = Counter()
for r in строки:
    try:
        d = json.loads(r["detail_json"] or "{}")
    except Exception:                                            # noqa: BLE001
        d = {}
    h = d.get("headers") or {}
    отпр = str(h.get("From") or "")
    м = re.search(r"[\w.+-]+@[\w.-]+\.\w+", отпр)
    адрес = (м.group(0).lower() if м else "")
    дом = адрес.split("@")[-1] if "@" in адрес else ""
    текст = str(d.get("snippet") or "").strip()
    тема = str(h.get("Subject") or "")
    if дом and дом in наши_дом:
        вид["домен ЕСТЬ в базе получателей"] += 1
        кандидаты.append((r["id"], str(r["event_ts"])[:16], адрес, тема[:40],
                          текст[:90]))
    elif дом in ПОЧТОВИКИ:
        вид["публичный почтовик"] += 1
        шум[дом] += 1
    elif not адрес:
        вид["отправитель не разобрался"] += 1
    else:
        вид["чужой домен"] += 1
        шум[дом] += 1
print("")
for к, n in вид.most_common():
    print("   %-36s %4d" % (к, n))
print("")
print("=== ЖИВЫЕ КАНДИДАТЫ (домен есть в базе): %d ===" % len(кандидаты))
for i, t, a, s, x in кандидаты:
    print("   #%-7s %s %-30s %s" % (i, t, a[:30], s))
    pass
print("")
print("=== топ чужих доменов (шум) ===")
for д, n in шум.most_common(8):
    print("   %-34s %3d" % (д[:34], n))
c.close()
