# -*- coding: utf-8 -*-
"""Сколько писем в отправке идёт на НЕПРОВЕРЕННЫЕ адреса.

Мой заслон спрашивал addr_probe и отбраковывал приговор «нет ящика» /
«нет MX». Но адрес, которого проба вообще не касалась, в addr_probe
отсутствует — и заслон пропускал его как чистый. Владелец просил
перекидывать ТОЛЬКО проверенные. Считаем разницу честно.

Проба тяжёлая (SMTP с VPS) — единственная, кто видит несуществующий ящик
на живом домене. Именно такие шесть адресов сегодня и отбились: 550
invalid mailbox.
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

ряды = c.execute(
    "SELECT m.id mid, m.campaign_id, m.status mst, r.email, "
    "       COALESCE(p.verdict,'') verdict, p.ts, "
    "       COALESCE(rc.mx_provider,'') mx "
    "FROM messages m "
    "JOIN confirm_reviews r ON r.message_id = m.id "
    "LEFT JOIN recipients rc ON rc.id = m.recipient_id "
    "LEFT JOIN addr_probe p ON p.email = lower(r.email) "
    "WHERE r.status IN ('approved','edited') "
    "AND m.status IN ('scheduled','sending')").fetchall()

счёт = Counter()
по_камп = Counter()
for r in ряды:
    в = str(r["verdict"] or "")
    ключ = в if в else "НЕ ПРОВЕРЕН ВОВСЕ"
    счёт[ключ] += 1
    if not в:
        по_камп[int(r["campaign_id"])] += 1

print(f"писем в отправке: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>4}  {k}")
print("\nнепроверенные по кампаниям:", dict(по_камп))

# Разрез по почтовику: именно публичные (mail.ru, yandex) проба и вскрывает.
пуб = Counter()
for r in ряды:
    if not str(r["verdict"] or ""):
        пуб[str(r["mx"] or "—")] += 1
print("непроверенные по почтовику:", dict(пуб.most_common(8)))

# Сколько всего вердиктов накопила проба — чтобы понимать её охват.
всего_проб = c.execute("SELECT COUNT(*) FROM addr_probe").fetchone()[0]
свежих = c.execute("SELECT COUNT(*) FROM addr_probe "
                   "WHERE substr(ts,1,10) >= date('now','-2 day')").fetchone()[0]
print(f"\nв addr_probe всего: {всего_проб} | за последние 2 дня: {свежих}")
