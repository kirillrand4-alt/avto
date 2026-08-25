# -*- coding: utf-8 -*-
"""Найти в очереди письма моей механической схемы.

Отпечаток однозначный: они кончаются просьбой переслать вместо канонической
строки отказа, и начинаются с представления, а не с наблюдения о компании.
Опусовые письма устроены наоборот.
"""
import sqlite3
import sys

СНЯТЬ = "--снять" in sys.argv
c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

строки = c.execute(
    "SELECT cr.id, cr.subject, cr.body, cr.created_at, cr.status, "
    "       r.company_name, m.id mid, COALESCE(m.status,'-') mst "
    "  FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    "  LEFT JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.status IN ('approved','pending') AND COALESCE(cr.body,'')<>''"
    ).fetchall()

мои = []
for р in строки:
    т = str(р["body"])
    без_отказа = "неактуальна, буду признателен за короткий ответ" not in т
    просьба = "перешлёте письмо коллеге" in т or "перешлёте письмо" in т
    начало_с_себя = False
    абз = [a.strip() for a in т.split("\n\n") if a.strip()]
    if len(абз) > 1:
        начало_с_себя = абз[1].startswith(("Я веду", "Меня зовут"))
    if без_отказа and (просьба or начало_с_себя):
        мои.append(р)

print("писем в очереди всего: %d" % len(строки))
print("похожи на мою механическую схему: %d" % len(мои))
from collections import Counter
print("\n=== ПО СОСТОЯНИЮ ПИСЬМА ===")
for к, н in Counter(str(р["mst"]) for р in мои).most_common():
    метка = "  ← УЙДЁТ" if к == "scheduled" else ""
    print("  письмо %-16s %5d%s" % (к, н, метка))
print("\n=== ПО ДАТЕ СОЗДАНИЯ ===")
for к, н in Counter(str(р["created_at"])[:10] for р in мои).most_common():
    print("  %s  %d" % (к, н))

print("\n=== ПРИМЕРЫ (первые 5) ===")
for р in мои[:5]:
    абз = [a.strip() for a in str(р["body"]).split("\n\n") if a.strip()]
    набл = next((a for a in абз if a.startswith("Смотрел, что выпускает")), "")
    print("  #%-6s %-32s письмо=%-10s %s"
          % (р["id"], str(р["company_name"] or "")[:32], р["mst"],
             набл[:90] or абз[1][:90] if len(абз) > 1 else ""))

if not СНЯТЬ:
    print("\nсухой прогон. Снять — --снять")
    raise SystemExit(0)

снято = 0
for р in мои:
    try:
        c.execute("UPDATE confirm_reviews SET status='skipped', "
                  "  decided_by='чистка механической схемы', "
                  "  decided_at=datetime('now'), "
                  "  reason='механическая сборка: склейка полей паспорта', "
                  "  updated_at=datetime('now') WHERE id=?", (р["id"],))
        if р["mid"]:
            c.execute("UPDATE messages SET status='skipped', "
                      "  last_error='чистка механической схемы', "
                      "  updated_at=datetime('now') "
                      " WHERE id=? AND status NOT IN ('sent','failed')", (р["mid"],))
        снято += 1
    except Exception as e:  # noqa: BLE001
        print("  #%s: %s" % (р["id"], str(e)[:80]))
c.commit()
print("\nснято: %d" % снято)
for р in c.execute("SELECT status, COUNT(*) n FROM messages "
                   " WHERE status NOT IN ('sent','skipped','failed') "
                   " GROUP BY status"):
    print("  письма %-14s %d" % (р["status"], р["n"]))
