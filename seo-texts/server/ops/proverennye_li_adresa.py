# -*- coding: utf-8 -*-
"""Были ли адреса проверены пробой ДО отправки - по дням.

Пять из семи сегодняшних отбивок - жёсткие 550 «invalid mailbox», то есть
ящика не существует. Такое ловит только SMTP-проба, и берёт она адреса
ТОЛЬКО из очереди подтверждения. Значит вопрос простой: какая доля писем
уходит с непроверенных адресов и растёт ли она.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
колонки = [р[1] for р in c.execute("PRAGMA table_info(addr_probe)")]
print("addr_probe:", ", ".join(колонки))
поле_а = "email" if "email" in колонки else колонки[0]
поле_в = next((k for k in ("verdict", "probe_verdict", "result") if k in колонки),
              None)
поле_т = next((k for k in ("ts", "checked_at", "updated_at", "created_at")
               if k in колонки), None)
проба = {}
for р in c.execute(f"SELECT {поле_а} a, {поле_в} v, {поле_т} t FROM addr_probe"):
    if р["a"]:
        проба[str(р["a"]).lower()] = (str(р["v"] or ""), str(р["t"] or ""))
print(f"вердиктов пробы в кэше панели: {len(проба)}")
print("раскладка вердиктов:",
      dict(Counter(v for v, _ in проба.values()).most_common(8)))

ряды = c.execute(
    "SELECT substr(COALESCE(m.sent_at,m.updated_at),1,10) день, r.email, "
    "       m.id mid, substr(COALESCE(m.sent_at,m.updated_at),1,19) когда "
    "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
    " WHERE m.status='sent' "
    "   AND substr(COALESCE(m.sent_at,m.updated_at),1,10) >= '2026-08-17'"
).fetchall()
отбились = {str(р[0] or "").lower() for р in c.execute(
    "SELECT r.email FROM events e JOIN recipients r ON r.id=e.recipient_id "
    "WHERE e.event_type='bounce'")}

по_дням = {}
for р in ряды:
    поч = str(р["email"] or "").lower()
    в, т = проба.get(поч, ("", ""))
    # проба считается «до отправки», если вердикт есть и он старше письма
    было = bool(в)
    ключ = "проверен" if было else "НЕ проверен"
    д = по_дням.setdefault(р["день"], Counter())
    д[ключ] += 1
    if поч in отбились:
        д[ключ + " -> отбился"] += 1

print(f"\n{'день':<12} {'проверено':>10} {'не проверено':>13} {'доля непров.':>13}")
for д in sorted(по_дням):
    п = по_дням[д]["проверен"]; н = по_дням[д]["НЕ проверен"]
    всего = п + н
    print(f"{д:<12} {п:>10} {н:>13} {(100.0*н/всего if всего else 0):>12.1f}%")
print("\nотбившиеся адреса по группам:")
for д in sorted(по_дням):
    print(f"  {д}: проверенные {по_дням[д]['проверен -> отбился']}, "
          f"непроверенные {по_дням[д]['НЕ проверен -> отбился']}")
