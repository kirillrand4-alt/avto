# -*- coding: utf-8 -*-
"""Где написанные письма: журнал против очереди подтверждения.

Владелец 24.08: «их было написано штук 30». Вопрос не про цену, а про
то, видит ли он их в очереди. Сверяем три вещи: сколько «итог» в
журнале, сколько строк в confirm_reviews за сегодня и в каком они
статусе — потому что карточка со статусом не pending из очереди
оператора пропадает.
"""
import io
import json
import sqlite3
import time
from collections import Counter

Ж = r"C:\sender\_ops\gen-partiya-935.jsonl"
СЕГОДНЯ = time.strftime("%Y-%m-%d")

итоги = []
for с in io.open(Ж, encoding="utf-8", errors="replace"):
    try:
        з = json.loads(с)
    except Exception:                                          # noqa: BLE001
        continue
    if з.get("этап") == "итог":
        итоги.append(з)

хвост = итоги[-60:]
print("строк «итог» в журнале всего: %d" % len(итоги))
print("последние 60 — review_id от %s до %s"
      % (хвост[0].get("review_id") if хвост else "-",
         хвост[-1].get("review_id") if хвост else "-"))
print("их статусы очереди при записи:",
      dict(Counter(з.get("статус_очереди", "?") for з in хвост)))
print("направления:", dict(Counter(з.get("направление", "?") for з in хвост)))

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("\n=== ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЯ ЗА СЕГОДНЯ ===")
for р in c.execute(
        "SELECT status, COUNT(*) n FROM confirm_reviews "
        "WHERE substr(created_at,1,10)=? GROUP BY status ORDER BY n DESC",
        (СЕГОДНЯ,)):
    print("  %-14s %d" % (р["status"], р["n"]))

всего = c.execute("SELECT COUNT(*) FROM confirm_reviews WHERE "
                  "substr(created_at,1,10)=?", (СЕГОДНЯ,)).fetchone()[0]
print("  ИТОГО за сегодня: %d" % всего)

print("\n=== ВСЯ ОЧЕРЕДЬ, НЕ ТОЛЬКО СЕГОДНЯ ===")
for р in c.execute("SELECT status, COUNT(*) n FROM confirm_reviews "
                   "GROUP BY status ORDER BY n DESC LIMIT 8"):
    print("  %-14s %d" % (р["status"], р["n"]))

print("\n=== ПОСЛЕДНИЕ 12 КАРТОЧЕК ===")
кол = {с[1] for с in c.execute("PRAGMA table_info(confirm_reviews)")}
поля = ["id", "status", "created_at"]
for д in ("recipient_id", "subject", "reason", "campaign_id"):
    if д in кол:
        поля.append(д)
зпр = "SELECT %s FROM confirm_reviews ORDER BY id DESC LIMIT 12" % ", ".join(поля)
for р in c.execute(зпр):
    строка = "  #%-6s %-12s %s" % (р["id"], р["status"], р["created_at"])
    if "subject" in поля:
        строка += " | %s" % str(р["subject"] or "")[:52]
    if "reason" in поля and р["reason"]:
        строка += " | причина: %s" % str(р["reason"])[:60]
    print(строка)
