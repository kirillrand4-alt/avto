# -*- coding: utf-8 -*-
"""Итог двух пачек: что с десятью и сколько отказов у вебинарных.

Хвост вывода обрезан по объёму, а знать надо точно: ушли ли десять
поправленных, и какая доля отказов вышла на вебинарных.
"""
import sqlite3
from collections import Counter

ДЕСЯТЬ = [3413, 3424, 3648, 3657, 3666, 3669, 3693, 3701, 3762, 3764]
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
print("=== десять поправленных ===")
for рид in ДЕСЯТЬ:
    р = c.execute(
        "SELECT cr.id, cr.status cst, cr.email, m.status mst, "
        "       COALESCE(m.last_error,'') err, substr(m.updated_at,1,19) когда "
        "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
        " WHERE cr.id=?", (рид,)).fetchone()
    print(f"  #{р['id']} {р['email']:<32} карточка={р['cst']:<9} "
          f"письмо={р['mst']:<8} {р['когда']}")
    if р["err"]:
        print(f"        {str(р['err'])[:120]}")

print("\n=== вебинарные ===")
ряды = c.execute(
    "SELECT cr.status cst, m.status mst, COALESCE(m.last_error,'') err "
    "  FROM confirm_reviews cr JOIN messages m ON m.id=cr.message_id "
    " WHERE cr.dedup_key LIKE 'vebinar28:%'").fetchall()
print("статусы:", dict(Counter(f"{р['cst']}/{р['mst']}" for р in ряды)))
спам = sum(1 for р in ряды if "suspicion of SPAM" in р["err"])
print(f"отказов «подозрение на спам» среди вебинарных: {спам}")

print("\n=== сегодня целиком ===")
ушло = c.execute(
    "SELECT COUNT(*) FROM messages WHERE status='sent' "
    "AND substr(COALESCE(sent_at,updated_at),1,10)='2026-08-21'").fetchone()[0]
отказ = c.execute(
    "SELECT COUNT(*) FROM messages WHERE COALESCE(last_error,'') LIKE "
    "'%suspicion of SPAM%' AND substr(updated_at,1,10)='2026-08-21'").fetchone()[0]
print(f"ушло {ушло}, отказов почтовика {отказ}, "
      f"доля {100.0*отказ/(ушло+отказ):.1f}%")
