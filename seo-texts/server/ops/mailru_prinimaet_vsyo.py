# -*- coding: utf-8 -*-
"""«Принимает всё» на mail.ru — это не «живой», это «узнать нельзя»."""
import io
import json
import sqlite3
from collections import Counter

партии = {}
for ф in (r"C:\sender\_ops\vtorye-adresa.jsonl", r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = json.loads(с)
            if "review" in d:
                партии[d["email"].lower()] = int(d["review"])
    except FileNotFoundError:
        pass
почты = sorted(партии)
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
вердикт = {}
for i in range(0, len(почты), 400):
    к = почты[i:i + 400]
    зн = ",".join("?" * len(к))
    for а, в in e.execute("SELECT email, probe_verdict FROM emails "
                          " WHERE email IN (%s)" % зн, к):
        а = (а or "").lower()
        # худший (информативнейший) вердикт по адресу
        пор = {"нет ящика": 4, "нет MX": 4, "есть": 3, "неясно": 2,
               "отказ пробе": 2, "принимает всё": 1}
        if пор.get(в or "", 0) > пор.get(вердикт.get(а, "") or "", 0):
            вердикт[а] = в
e.close()

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
s.row_factory = sqlite3.Row
mx = {}
статус = {}
for i in range(0, len(почты), 400):
    к = почты[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in s.execute("SELECT email, mx_provider FROM recipients "
                       " WHERE email IN (%s)" % зн, к):
        mx[(r["email"] or "").lower()] = str(r["mx_provider"] or "?")
зн2 = ",".join("?" * len(партии))
for r in s.execute("SELECT id, status FROM confirm_reviews WHERE id IN (%s)" % зн2,
                   list(партии.values())):
    статус[int(r["id"])] = r["status"]

пары = Counter()
риск = 0
for а in почты:
    в = вердикт.get(а) or "вердикта нет"
    п = mx.get(а, "?")
    пары[(п, в)] += 1
    if в == "принимает всё" and п == "mailru" and \
            статус.get(партии[а]) in ("pending", "approved"):
        риск += 1
print("адресов в партиях: %d" % len(почты))
print("")
print("=== почтовик × вердикт пробы (топ) ===")
for (п, в), n in пары.most_common(12):
    print("   %-12s %-16s %5d" % (п[:12], в, n))
print("")
print("В РАБОТЕ (pending/approved) на mail.ru с «принимает всё»: %d" % риск)

# исторический процент отбивок по такому сочетанию
print("")
print("=== отбивки за всё время: mail.ru против остальных ===")
for пров in ("mailru", "yandex", "google"):
    всего = s.execute(
        "SELECT COUNT(*) FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='sent' AND r.mx_provider=?", (пров,)).fetchone()[0]
    отб = s.execute(
        "SELECT COUNT(DISTINCT e.recipient_id) FROM events e "
        "  JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND r.mx_provider=?", (пров,)).fetchone()[0]
    if всего:
        print("   %-10s отправлено %5d, отбилось %4d (%.1f%%)"
              % (пров, всего, отб, 100.0 * отб / всего))
s.close()
