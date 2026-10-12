# -*- coding: utf-8 -*-
"""Как раньше писали письма Meyer, опираясь на паспорт сайта.

Владелец 12.10: «посмотри как писали раньше по паспорту». Берём реально
отправленные письма Meyer компаниям, у которых в обогащении есть паспорт,
и показываем по одному примеру на отрасль (отрасль — по книгам).

Запуск: kak_pisali_po_pasportu.py [срез]   срез 0 — первый пример, 1 — второй.
"""
import glob
import io
import json
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.store import Store                                  # noqa: E402

СРЕЗ = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
ПОЛОВИНА = sys.argv[2] if len(sys.argv) > 2 else "все"

отрасль = {}
for п in sorted(glob.glob(r"C:\sender\server\ops\knigi2_*.json")):
    for к in (json.load(io.open(п, encoding="utf-8")).get("компании") or []):
        if к.get("otrasl"):
            отрасль[к["inn"]] = к["otrasl"]

cx = sqlite3.connect(r"C:\sender\enrich.db", timeout=60)
cx.row_factory = sqlite3.Row
есть_паспорт = {р["inn"] for р in cx.execute(
    "SELECT inn FROM companies WHERE activity IS NOT NULL "
    "AND length(activity) > 200")}
cx.close()

store = Store(r"C:\sender\sender.db")
примеры = {}
with store._lock:
    c = store._conn
    for р in c.execute(
            "SELECT m.subject s, m.body_rendered b, r.inn i, r.company_name n "
            "  FROM messages m JOIN recipients r ON m.recipient_id = r.id "
            " WHERE m.status='sent' AND m.body_rendered IS NOT NULL "
            " ORDER BY m.id DESC LIMIT 20000"):
        инн = str(р["i"] or "")
        о = отрасль.get(инн)
        if not о or инн not in есть_паспорт:
            continue
        примеры.setdefault(о, []).append((р["n"], р["s"], р["b"]))

имена = sorted(примеры)
if ПОЛОВИНА == "a":
    имена = имена[:len(имена) // 2]
elif ПОЛОВИНА == "b":
    имена = имена[len(имена) // 2:]
print("отраслей с примерами: %d (показываю %d, срез %d)"
      % (len(примеры), len(имена), СРЕЗ))
for о in имена:
    сп = примеры[о]
    if СРЕЗ >= len(сп):
        continue
    имя, тема, тело = сп[СРЕЗ]
    тело = " ".join(str(тело or "").split())
    print("")
    print("### %s  [писем с паспортом: %d]" % (о, len(сп)))
    print("    компания: %s" % str(имя)[:60])
    print("    тема: %s" % str(тема or "")[:90])
    print("    %s" % тело[:700])
