# -*- coding: utf-8 -*-
"""Что проба говорила про отбившиеся адреса + поиск таких же опечаток."""
import io
import json
import sqlite3
from collections import Counter

ОТБИЛИСЬ = ["zakaz@proeda.ru", "nfo@bstdom.ru", "n.lavrenteva@sibgaz.ru"]
e = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\enrich.db", uri=True, timeout=60)
e.row_factory = sqlite3.Row
print("=== что проба знала про отбившиеся ===")
for а in ОТБИЛИСЬ:
    r = e.execute("SELECT email, probe_verdict, probe_ts, mx_ok, source, source_url "
                  "  FROM emails WHERE email=? LIMIT 1", (а,)).fetchone()
    if r is None:
        print("   %-28s в обогащении НЕТ" % а)
        continue
    print("   %-28s вердикт: %-16s mx=%s  источник: %s"
          % (а, r["probe_verdict"] or "—", r["mx_ok"], str(r["source"] or "")[:28]))


# были ли эти адреса вообще у нас проверены и что стояло в стоп-листе
sq = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=60)
sq.row_factory = sqlite3.Row
print("")
print("=== в базе рассылки ===")
for а in ОТБИЛИСЬ:
    r = sq.execute("SELECT id, valid_status, catch_all, mx_provider, source "
                   "  FROM recipients WHERE email=? LIMIT 1", (а,)).fetchone()
    if r:
        print("   %-28s valid=%s catch_all=%s mx=%s источник=%s"
              % (а, r["valid_status"], r["catch_all"], str(r["mx_provider"])[:14],
                 str(r["source"])[:16]))
    st = sq.execute("SELECT reason, source, created_at FROM suppression "
                    " WHERE value=? ORDER BY id DESC LIMIT 1", (а,)).fetchone()
    print("      стоп-лист: %s" % (dict(st) if st else "нет"))
# сколько адресов партий имеют вердикт пробы вообще
import json as _j
партии = {}
for ф in (r"C:\sender\_ops\vtorye-adresa.jsonl", r"C:\sender\_ops\vtorye-adresa-2.jsonl"):
    try:
        for с in io.open(ф, encoding="utf-8"):
            d = _j.loads(с)
            if "review" in d:
                партии[d["email"]] = 1
    except FileNotFoundError:
        pass
почты = list(партии)
из_проб = Counter()
for i in range(0, len(почты), 400):
    к = почты[i:i + 400]
    зн = ",".join("?" * len(к))
    for r in e.execute("SELECT email, probe_verdict FROM emails "
                       " WHERE email IN (%s)" % зн, к):
        из_проб[r["probe_verdict"] or "вердикта нет"] += 1
print("")
print("=== вердикты пробы по адресам партий (%d) ===" % len(почты))
for к, n in из_проб.most_common():
    print("   %-20s %5d  (%.0f%%)" % (к, n, 100.0 * n / len(почты)))
print("   не найдено в обогащении: %d" % (len(почты) - sum(из_проб.values())))
sq.close()
e.close()
