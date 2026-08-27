# -*- coding: utf-8 -*-
"""Какие карточки станут источником копии: холодные или рассылочные."""
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender\sender")
exec(open(r"C:\sender\server\ops\zapas_kopiy_3dnya.py", encoding="utf-8")
     .read().split("print(\"\")\nprint(\"=== отсев адресов ===\")")[0])
выбор = {инн: sorted(v)[0] for инн, v in годные.items()}

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True, timeout=90)
c.row_factory = sqlite3.Row
вид = Counter()
ключи = Counter()
for инн in выбор:
    r = c.execute(
        "SELECT cr.dedup_key, cr.subject FROM confirm_reviews cr "
        "  JOIN messages m ON m.id = cr.message_id "
        " WHERE cr.inn=? AND m.status='sent' AND COALESCE(cr.body,'')<>'' "
        " ORDER BY m.sent_at ASC LIMIT 1", (инн,)).fetchone()
    if r is None:
        вид["нет карточки"] += 1
        continue
    к = str(r["dedup_key"] or "")
    ключи[к.split(":")[0][:18] if ":" in к else "без префикса"] += 1
    вид["рассылка/вебинар" if "vebinar" in к.lower() else "холодное"] += 1
print("")
print("=== источник копии ===")
for к, n in вид.most_common():
    print("   %-24s %5d" % (к, n))
print("")
print("=== префиксы dedup_key ===")
for к, n in ключи.most_common(8):
    print("   %-24s %5d" % (к, n))
# у скольких есть холодная карточка помимо рассылочной
есть_холод = 0
for инн in выбор:
    n = c.execute(
        "SELECT COUNT(*) FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.inn=? AND m.status='sent' AND COALESCE(cr.body,'')<>'' "
        "   AND LOWER(COALESCE(cr.dedup_key,'')) NOT LIKE '%vebinar%'",
        (инн,)).fetchone()[0]
    if n:
        есть_холод += 1
print("")
print("компаний, у которых ЕСТЬ отправленное холодное письмо: %d из %d"
      % (есть_холод, len(выбор)))
c.close()
