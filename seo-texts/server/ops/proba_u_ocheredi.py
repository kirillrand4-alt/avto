# -*- coding: utf-8 -*-
"""Проверена ли SMTP-проба у адресов, которые стоят в очереди и на отправке."""
import sqlite3
from collections import Counter, defaultdict

c = sqlite3.connect("file:%s?mode=ro" % r"C:\sender\sender.db", uri=True,
                    timeout=90)
c.row_factory = sqlite3.Row
пробы = {}
for r in c.execute("SELECT email, verdict, ts FROM addr_probe"):
    а = str(r["email"] or "").strip().lower()
    if а:
        пробы[а] = (str(r["verdict"] or ""), str(r["ts"] or ""))
print("адресов с пробой в базе: %d" % len(пробы))

print("\n=== ОЧЕРЕДЬ ПОДТВЕРЖДЕНИЙ ===")
свод = defaultdict(Counter)
без_пробы = defaultdict(list)
for r in c.execute("SELECT id, campaign_id, status, email FROM confirm_reviews"
                   " WHERE status IN ('pending','approved','edited')"):
    а = str(r["email"] or "").strip().lower()
    в = пробы.get(а, (None, None))[0]
    ключ = "%s / кампания %s" % (r["status"], r["campaign_id"])
    свод[ключ][в or "ПРОБЫ НЕТ"] += 1
    if not в:
        без_пробы[ключ].append(r["id"])
for к in sorted(свод):
    всего = sum(свод[к].values())
    нет = свод[к]["ПРОБЫ НЕТ"]
    print("   %-26s всего %5d, без пробы %5d (%.0f%%)"
          % (к, всего, нет, 100.0 * нет / всего))
    for в, n in свод[к].most_common():
        if в != "ПРОБЫ НЕТ":
            print("        %-24s %5d" % (в, n))

print("\n=== ПИСЬМА В ОТПРАВКЕ ===")
свод2 = defaultdict(Counter)
for r in c.execute("SELECT m.id, m.campaign_id, m.status, r.email"
                   "  FROM messages m JOIN recipients r ON r.id=m.recipient_id"
                   " WHERE m.status IN ('scheduled','sending','pending_review')"):
    а = str(r["email"] or "").strip().lower()
    в = пробы.get(а, (None, None))[0]
    свод2["%s / кампания %s" % (r["status"], r["campaign_id"])][в or "ПРОБЫ НЕТ"] += 1
for к in sorted(свод2):
    всего = sum(свод2[к].values())
    нет = свод2[к]["ПРОБЫ НЕТ"]
    print("   %-30s всего %5d, без пробы %5d (%.0f%%)"
          % (к, всего, нет, 100.0 * нет / всего))
    for в, n in свод2[к].most_common():
        if в != "ПРОБЫ НЕТ":
            print("        %-24s %5d" % (в, n))

print("\n=== ПРИГОВОРЁННЫЕ, КОТОРЫЕ ВСЁ ЕЩЁ В ОЧЕРЕДИ ===")
опасные = list(c.execute(
    "SELECT cr.id, cr.campaign_id, cr.status, cr.email FROM confirm_reviews cr"
    " WHERE cr.status IN ('pending','approved','edited')"))
плохие = [s for s in опасные
          if пробы.get(str(s["email"] or "").strip().lower(), ("", ""))[0]
          in ("нет ящика", "нет MX")]
print("   писем на адреса с приговором: %d" % len(плохие))
for s in плохие[:10]:
    print("      review %s  кампания %s  %-10s %s"
          % (s["id"], s["campaign_id"], s["status"], s["email"]))

свежие = list(c.execute(
    "SELECT id, email FROM confirm_reviews WHERE campaign_id=11"
    "   AND created_at >= datetime('now','-4 hour')"))
c.close()
нет_св = sum(1 for s in свежие
             if str(s["email"] or "").strip().lower() not in пробы)
print("\n=== ИТОГ ===")
print("сегодняшняя партия Meyer: %d писем, без пробы %d (%.0f%%)"
      % (len(свежие), нет_св, 100.0 * нет_св / len(свежие) if свежие else 0))
print("писем на приговорённые адреса в живой очереди: %d" % len(плохие))
