# -*- coding: utf-8 -*-
"""Кого из очереди работник проверял НА САМОМ ДЕЛЕ — по его файлу.

Справка соседней сессии: в addr_probe вердикт мог попасть и не от
работника (отбивка пишет туда же), а ts там — время импорта, не пробы.
Единственный честный источник «работник это видел» — его собственный
probe-rezultat.jsonl на дропе, где у каждой строки свой ts.
"""
import io
import json
import os
import sqlite3
import urllib.request
from collections import Counter

ДРОП = os.environ.get("DROP_URL", "https://parsercompressor.online/drop")
ТОКЕН = os.environ.get("DROP_TOKEN", "")
ФАЙЛ = r"C:\sender\_ops\probe-rezultat.jsonl"

if not os.path.exists(ФАЙЛ) or os.path.getsize(ФАЙЛ) < 1000:
    зпр = urllib.request.Request(ДРОП.rstrip("/") + "/probe-rezultat.jsonl",
                                 headers={"X-Drop-Token": ТОКЕН})
    with urllib.request.urlopen(зпр, timeout=600) as о, \
            open(ФАЙЛ, "wb") as f:
        f.write(о.read())
print(f"файл работника: {os.path.getsize(ФАЙЛ)} байт")

видел = {}
for s in io.open(ФАЙЛ, encoding="utf-8", errors="replace"):
    try:
        z = json.loads(s)
    except Exception:                                            # noqa: BLE001
        continue
    e = str(z.get("email") or "").strip().lower()
    if e:
        видел[e] = str(z.get("verdict") or z.get("вердикт") or "")
print(f"адресов в файле работника: {len(видел)}")

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.email, COALESCE(p.verdict,'') v "
    "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
    "LEFT JOIN addr_probe p ON p.email=lower(cr.email) "
    "WHERE cr.status IN ('approved','edited') "
    "AND m.status IN ('scheduled','sending')").fetchall()

счёт = Counter()
for r in ряды:
    e = str(r["email"] or "").strip().lower()
    в = видел.get(e)
    if в is None:
        счёт["РАБОТНИК НЕ ВИДЕЛ"] += 1
    else:
        счёт[f"работник: {в or '—'}"] += 1
print(f"\nждут отправки: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
