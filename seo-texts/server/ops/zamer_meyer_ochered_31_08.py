# -*- coding: utf-8 -*-
"""Только чтение: очередь по кампаниям + резюм журнала партии.

Отвечает на один вопрос: нужна ли ещё сотня писем Meyer, или готовое
уже стоит в очереди. Ничего не меняет.
"""
import io
import json
import os
import sqlite3
from collections import Counter

БД = r"C:\sender\sender.db"
ЖУРНАЛ = r"C:\sender\_ops\gen-partiya-935.jsonl"
c = sqlite3.connect(БД)
c.row_factory = sqlite3.Row


def колонки(т):
    try:
        return [r["name"] for r in c.execute(f"PRAGMA table_info({т})")]
    except Exception:
        return []


кол_cr, кол_m = колонки("confirm_reviews"), колонки("messages")
print("=== СХЕМА ===")
print("  confirm_reviews:", ", ".join(кол_cr))
print("  messages       :", ", ".join(кол_m))

# связь confirm_reviews -> кампания
связь = None
if "campaign_id" in кол_cr:
    связь = "cr.campaign_id"
elif "message_id" in кол_cr and "campaign_id" in кол_m:
    связь = "m.campaign_id"

итог = []
if связь:
    join = "" if связь.startswith("cr.") else " LEFT JOIN messages m ON m.id = cr.message_id"
    print("\n=== confirm_reviews ПО КАМПАНИЯМ ===")
    for р in c.execute(f"SELECT {связь} k, cr.status s, COUNT(*) n"
                       f"  FROM confirm_reviews cr{join}"
                       f" GROUP BY k, s ORDER BY k, n DESC"):
        if р["k"] in (10, 11):
            print("  кампания %-4s %-14s %5d" % (р["k"], р["s"], р["n"]))
            итог.append((р["k"], р["s"], р["n"]))

if "campaign_id" in кол_m:
    print("\n=== messages ПО КАМПАНИЯМ ===")
    for р in c.execute("SELECT campaign_id k, status s, COUNT(*) n FROM messages"
                       " GROUP BY k, s ORDER BY k, n DESC"):
        if р["k"] in (10, 11):
            print("  кампания %-4s %-14s %5d" % (р["k"], р["s"], р["n"]))

# --- журнал партии -------------------------------------------------------
print("\n=== ЖУРНАЛ ПАРТИИ (%s) ===" % ЖУРНАЛ)
по_дням = Counter()
цена_дня = Counter()
ок_дня = Counter()
напр = Counter()
всего = 0
if os.path.exists(ЖУРНАЛ):
    for s in io.open(ЖУРНАЛ, encoding="utf-8"):
        try:
            z = json.loads(s)
        except Exception:
            continue
        if z.get("этап") == "итог":
            continue
        всего += 1
        д = str(z.get("когда") or z.get("ts") or "")[:10]
        по_дням[д] += 1
        if z.get("ок"):
            ок_дня[д] += 1
        цена_дня[д] += float(z.get("цена_$") or 0)
        напр[str(z.get("направление"))] += 1
    print("  строк всего: %d" % всего)
    print("  %-12s %7s %7s %7s %9s" % ("день", "обраб.", "годных", "отдача", "цена $"))
    for д in sorted(по_дням, reverse=True)[:8]:
        n, k = по_дням[д], ок_дня[д]
        print("  %-12s %7d %7d %6.0f%% %9.2f" % (д, n, k, 100.0 * k / max(1, n), цена_дня[д]))
    print("  по направлениям:", dict(напр))
else:
    print("  журнала нет")

print("\n=== ИТОГ ===")
св = {}
for k, s, n in итог:
    св.setdefault(k, {})[s] = n
for k in (10, 11):
    d = св.get(k, {})
    имя = "КЦ" if k == 10 else "Meyer"
    print("  кампания %-2d %-6s pending=%-5d approved=%-5d sent=%-5d skipped=%-5d"
          % (k, имя, d.get("pending", 0), d.get("approved", 0),
             d.get("sent", 0), d.get("skipped", 0)))
