# -*- coding: utf-8 -*-
"""Точный список писем моей механической схемы — по её же журналу.

Отпечаток по структуре оказался слишком широким: под «нет строки отказа +
начинается с представления» попадают ВСЕ законные мейеровские письма, у
них это канон. Гадать нельзя, поэтому берём номера карточек из durable-
журнала самой схемы, который она писала с fsync.
"""
import io
import json
import sqlite3
import sys
from collections import Counter

СНЯТЬ = "--снять" in sys.argv
ОТЧЁТ = r"C:\sender\_ops\deshevaya-partiya.jsonl"
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

мои = {}
for с in io.open(ОТЧЁТ, encoding="utf-8"):
    с = с.strip()
    if not с:
        continue
    try:
        з = json.loads(с)
    except Exception:  # noqa: BLE001
        continue
    if з.get("ок") and з.get("review_id"):
        мои[int(з["review_id"])] = з
print("карточек, положенных механической схемой: %d" % len(мои))

живые, состояние = [], Counter()
for rid, з in мои.items():
    р = c.execute(
        "SELECT cr.id, cr.status, r.company_name, COALESCE(m.status,'-') mst, "
        "       m.id mid FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN messages m ON m.id=cr.message_id WHERE cr.id=?",
        (rid,)).fetchone()
    if not р:
        continue
    состояние["карточка %s / письмо %s" % (р["status"], р["mst"])] += 1
    if р["status"] in ("approved", "pending") and р["mst"] not in ("sent", "skipped"):
        живые.append(р)

print("\n=== ГДЕ ОНИ СЕЙЧАС ===")
for к, н in состояние.most_common():
    метка = "  ← УЙДЁТ" if "scheduled" in к else ""
    print("  %-42s %5d%s" % (к, н, метка))
print("\nживых (могут уйти): %d" % len(живые))
for р in живые[:8]:
    print("  #%-6s %-36s письмо %s" % (р["id"],
                                       str(р["company_name"] or "")[:36], р["mst"]))

if not СНЯТЬ:
    print("\nсухой прогон. Снять — --снять")
    raise SystemExit(0)

снято = 0
for р in живые:
    c.execute("UPDATE confirm_reviews SET status='skipped', "
              "  decided_by='чистка механической схемы', decided_at=datetime('now'), "
              "  reason='механическая сборка: склейка полей паспорта (Мебель ДПК)', "
              "  updated_at=datetime('now') WHERE id=?", (р["id"],))
    if р["mid"]:
        c.execute("UPDATE messages SET status='skipped', "
                  "  last_error='чистка механической схемы', updated_at=datetime('now') "
                  " WHERE id=? AND status NOT IN ('sent','failed')", (р["mid"],))
    снято += 1
c.commit()
print("\nснято: %d" % снято)
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   " WHERE status NOT IN ('sent','skipped','failed') GROUP BY status"):
    print("  письма %-14s %d" % (р["status"], р["n"]))
