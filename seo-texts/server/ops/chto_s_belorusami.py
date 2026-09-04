# -*- coding: utf-8 -*-
"""Что стало с белорусскими компаниями каталога ProdExpo: письма, отправки, ответы."""
import io
import json
import os
import sqlite3
from collections import Counter

ГРУППА = "prodexpo2025"
КАРТОЧКИ = r"C:\sender\_ops\belarus\kartochki.jsonl"
ЗАЛИТО = r"C:\sender\_ops\belarus\zalito.jsonl"
ЖУРНАЛ_ГЕН = r"C:\sender\_ops\gen-partiya-935.jsonl"

карточек = залито = 0
for п, имя in ((КАРТОЧКИ, "карточки"), (ЗАЛИТО, "залито")):
    if os.path.exists(п):
        n = sum(1 for с in io.open(п, encoding="utf-8", errors="replace")
                if с.strip())
        if имя == "карточки":
            карточек = n
        else:
            залито = n

s = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=120)
s.row_factory = sqlite3.Row
получатели = [dict(r) for r in s.execute(
    "SELECT * FROM recipients WHERE COALESCE(extra_json,'') LIKE ? "
    "   OR COALESCE(source,'') LIKE ? OR inn LIKE '9990%'",
    ("%%%s%%" % ГРУППА, "%%%s%%" % ГРУППА))]
ключи = {str(р["inn"]) for р in получатели}
ридс = {int(р["id"]) for р in получатели}

письма = [dict(r) for r in s.execute(
    "SELECT * FROM confirm_reviews WHERE inn IN (%s)"
    % ",".join("?" * len(ключи)), tuple(ключи))] if ключи else []
отправки = [dict(r) for r in s.execute(
    "SELECT * FROM send_log WHERE inn IN (%s)"
    % ",".join("?" * len(ключи)), tuple(ключи))] if ключи else []
события = [dict(r) for r in s.execute(
    "SELECT * FROM events WHERE recipient_id IN (%s)"
    % ",".join("?" * len(ридс)), tuple(ридс))] if ридс else []
лиды = [dict(r) for r in s.execute(
    "SELECT * FROM leads WHERE inn IN (%s)"
    % ",".join("?" * len(ключи)), tuple(ключи))] if ключи else []
s.close()

в_журнале = Counter()
if os.path.exists(ЖУРНАЛ_ГЕН):
    for с in io.open(ЖУРНАЛ_ГЕН, encoding="utf-8", errors="replace"):
        try:
            z = json.loads(с)
        except Exception:                                      # noqa: BLE001
            continue
        if str(z.get("inn") or "") in ключи and z.get("этап") == "итог":
            в_журнале["ок" if z.get("ок") else "брак"] += 1

print("=" * 78)
print("=== СВОДКА: БЕЛОРУССКИЕ КОМПАНИИ (каталог ProdExpo) ===")
print("карточек разобрано из каталога: %d" % карточек)
print("залито в базу (журнал заливки):  %d" % залито)
print("получателей в панели:            %d" % len(получатели))
print("   из них со своим ключом 9990:  %d"
      % sum(1 for р in получатели if str(р["inn"]).startswith("9990")))
print("")
print("=== ПИСЬМА ===")
print("карточек подтверждения: %d" % len(письма))
for к, в in Counter(str(п.get("status")) for п in письма).most_common():
    print("   %-16s %4d" % (к, в))
print("генерация по журналу: %s" % dict(в_журнале))
print("")
print("=== ОТПРАВКИ ===")
print("строк в send_log: %d" % len(отправки))
for к, в in Counter(str(о.get("outcome")) for о in отправки).most_common():
    print("   %-16s %4d" % (к, в))
print("")
print("=== ОТВЕТЫ И ЛИДЫ ===")
for к, в in Counter(str(с.get("event_type")) for с in события).most_common():
    print("   событие %-14s %4d" % (к, в))
print("лидов: %d" % len(лиды))
for л in лиды[:8]:
    print("   %-34s %-16s %s"
          % (str(л.get("company_name"))[:34], str(л.get("status")),
             str(л.get("need") or "").replace("\n", " ")[:60]))
print("")
print("=== ПРИМЕРЫ КОМПАНИЙ ===")
for р in получатели[:8]:
    print("   %-13s %-38s %s"
          % (str(р.get("inn")), str(р.get("company_name"))[:38],
             str(р.get("email"))[:34]))
