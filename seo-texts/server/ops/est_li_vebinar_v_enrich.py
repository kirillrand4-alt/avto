# -*- coding: utf-8 -*-
"""Есть ли компании вебинара в enrich.db - и открывается ли она вообще.

Две разные беды выглядят в панели похоже: «enrich недоступен» (база не
открылась) и «нет данных компании в карточке» (база открылась, строки по
ИНН нет). Различаем прямым запросом.
"""
import sqlite3
import sys

sys.path.insert(0, r"C:\sender")
from sender.config import Config                              # noqa: E402
from sender.store import Store                                # noqa: E402

cfg = Config.load(r"C:\sender\sender.yaml")
store = Store(cfg.get("service.db_path", r"C:\sender\sender.db"))
with store._lock:
    инны = [р[0] for р in store._conn.execute(
        "SELECT DISTINCT inn FROM confirm_reviews "
        " WHERE dedup_key LIKE 'vebinar28:%' AND inn<>''").fetchall()]
print(f"ИНН у карточек вебинара: {len(инны)}")

путь = r"C:\sender\enrich.db"
try:
    к = sqlite3.connect(f"file:{путь}?mode=ro", uri=True, timeout=20)
except Exception as ex:                                       # noqa: BLE001
    print(f"enrich.db НЕ ОТКРЫЛАСЬ: {type(ex).__name__} {str(ex)[:120]}")
    raise SystemExit(0)
print("enrich.db открылась")
таблицы = [р[0] for р in к.execute(
    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("таблицы:", ", ".join(т for т in таблицы if т in
                            ("companies", "emails", "signals", "persons"))
      or "нужных нет")

for т, поле in (("companies", "inn"), ("emails", "inn"),
                ("persons", "inn")):
    if т not in таблицы:
        continue
    метки = ",".join("?" * len(инны))
    есть = к.execute(
        f"SELECT COUNT(DISTINCT {поле}) FROM {т} WHERE {поле} IN ({метки})",
        инны).fetchone()[0]
    всего = к.execute(f"SELECT COUNT(*) FROM {т}").fetchone()[0]
    print(f"{т}: наших {есть} из {len(инны)} (в таблице всего {всего})")

нет = [и for и in инны if not к.execute(
    "SELECT 1 FROM companies WHERE inn=? LIMIT 1", (и,)).fetchone()] \
    if "companies" in таблицы else []
print(f"\nбез строки в companies: {len(нет)}")
for и in нет[:12]:
    print(f"  {и}")
