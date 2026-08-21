# -*- coding: utf-8 -*-
"""Сырой разбор отбивок: жёсткие/мягкие, коды, диагностика, история.

Вердикт в событии - «dsn», а решает всё то, что внутри: 5.1.1 «нет такого
ящика» - это качество списка, 5.7.1/554 - это репутация, 4.x - временное.
Печатаем detail_json как есть, плюс те же ключи за последние 10 дней, чтобы
увидеть, изменилась ли ПРИРОДА отбивок, а не только их доля.
"""
import json
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT e.id, substr(COALESCE(e.event_ts,e.created_at),1,10) день, "
    "       COALESCE(e.detail_json,'') dj, r.email "
    "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
    " WHERE e.event_type='bounce' "
    "   AND substr(COALESCE(e.event_ts,e.created_at),1,10) >= '2026-08-11' "
    " ORDER BY e.id").fetchall()

def разбор(dj):
    try:
        д = json.loads(dj or "{}")
    except Exception:                                              # noqa: BLE001
        return {}, ""
    плоско = json.dumps(д, ensure_ascii=False)
    return д, плоско

коды = Counter(); типы = Counter(); по_дням = {}
print("=== сегодняшние отбивки целиком ===")
for р in ряды:
    д, плоско = разбор(р["dj"])
    м = re.search(r"\b([45]\.\d{1,3}\.\d{1,3})\b", плоско)
    код = м.group(1) if м else ""
    жёсткость = ("жёсткая" if код.startswith("5") else
                 "мягкая" if код.startswith("4") else "не понял")
    коды[код or "нет кода"] += 1
    типы[жёсткость] += 1
    по_дням.setdefault(р["день"], Counter())[жёсткость] += 1
    if р["день"] == "2026-08-21":
        print(f"\n#{р['id']} {р['email']}  код={код or '-'} ({жёсткость})")
        print(f"  {плоско[:600]}")

print("\n=== коды за 11.08-21.08 ===")
for к, н in коды.most_common():
    print(f"  {н:>3}  {к}")
print("\n=== жёсткость по дням ===")
for д in sorted(по_дням):
    print(f"  {д}: {dict(по_дням[д])}")
