# -*- coding: utf-8 -*-
"""Сколько писем ЯНДЕКС не принял у нас как спам (554 5.7.1) - по дням и доменам.

Это не отбивка получателя. 554 отдаёт НАШ почтовик на выходе: письмо не
ушло вовсе. Такой отказ - прямая оценка нашей репутации, и если он идёт
пачками, доталкивать ещё писем через тот же домен - худшее из возможного.

Считаем честно: по messages.last_error, по дням, по ящикам и доменам, и
отдельно долю от попыток дня.
"""
import re
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT m.id, m.mailbox_id, m.campaign_id, m.status, "
    "       substr(COALESCE(m.updated_at,m.created_at),1,10) день, "
    "       COALESCE(m.last_error,'') err "
    "  FROM messages m WHERE COALESCE(m.last_error,'') <> ''").fetchall()
спам = [р for р in ряды if "554" in р["err"] and "suspicion of SPAM" in р["err"]]
print(f"писем с ошибкой всего: {len(ряды)}")
print(f"ОТКАЗОВ ЯНДЕКСА «подозрение на спам» (554 5.7.1): {len(спам)}\n")

ушло_по_дням = Counter(str(р[0]) for р in c.execute(
    "SELECT substr(COALESCE(sent_at,updated_at),1,10) FROM messages "
    "WHERE status='sent'"))
print(f"{'день':<12} {'отказов':>8} {'ушло':>6} {'доля отказов':>14}")
for д, н in sorted(Counter(str(р["день"]) for р in спам).items()):
    у = ушло_по_дням.get(д, 0)
    print(f"{д:<12} {н:>8} {у:>6} {(100.0*н/(н+у) if (н+у) else 0):>13.1f}%")

print("\nпо ящикам:")
for я, н in Counter(str(р["mailbox_id"]) for р in спам).most_common():
    print(f"  {н:>4}  {я}")
print("\nпо доменам отправителя:")
for д, н in Counter(str(р["mailbox_id"]).split("@")[-1] for р in спам).most_common():
    print(f"  {н:>4}  {д}")
print("\nпо кампаниям:", dict(Counter(f"камп{р['campaign_id']}" for р in спам)))
print("статусы этих писем:", dict(Counter(str(р["status"]) for р in спам)))

дом_получателя = Counter(str(р["err"]).split("@")[-1][:14] for р in спам)
print("\nпервые пять ошибок целиком:")
for р in спам[:5]:
    print(f"  msg{р['id']} {р['mailbox_id']}: {str(р['err'])[:150]}")
