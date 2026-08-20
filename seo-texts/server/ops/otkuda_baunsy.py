# -*- coding: utf-8 -*-
"""Откуда прилетели баунсы: адрес, ящик, кампания, текст отбивки.

Владелец 20.08: «проверь 2 баунса откуда они». Смотрим события типа
bounce за последние дни: кому писали, с какого ящика, что ответил сервер
получателя и что с адресом сделали дальше.
"""
import sqlite3
import sys
from collections import Counter

СКОЛЬКО = int(next((a for a in sys.argv[1:] if a.isdigit()), "12"))
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row

print("== события bounce, последние ==")
ряды = c.execute(
    "SELECT e.id, e.message_id, e.event_ts, e.created_at, "
    "       e.detail_json, e.mailbox_id embox, e.provider, "
    "       m.campaign_id, m.mailbox_id, m.recipient_id, "
    "       r.email, r.company_name, r.inn, r.mx_provider "
    "FROM events e "
    "LEFT JOIN messages m ON m.id = e.message_id "
    "LEFT JOIN recipients r ON r.id = m.recipient_id "
    "WHERE e.event_type='bounce' "
    "ORDER BY e.id DESC LIMIT ?", (СКОЛЬКО,)).fetchall()
print(f"найдено: {len(ряды)}")
for r in ряды:
    print("-" * 74)
    print(f"  {str(r['created_at'])[:19]} | письмо #{r['message_id']} | "
          f"кампания {r['campaign_id']} | ящик "
          f"{r['mailbox_id'] or r['embox']} | {r['provider'] or ''}")
    print(f"  кому: {r['email']} | {str(r['company_name'] or '')[:40]} | "
          f"ИНН {r['inn']} | MX {r['mx_provider']}")
    п = str(r["detail_json"] or "")
    print(f"  отбивка: {п[:600]}")

print("\n== что с этими адресами сейчас ==")
for r in ряды:
    e = str(r["email"] or "").lower()
    if not e:
        continue
    s = c.execute("SELECT reason, created_at FROM suppression WHERE value=? "
                  "OR value=?", (e, e.split("@")[-1])).fetchall()
    p = c.execute("SELECT verdict, ts FROM addr_probe WHERE email=?",
                  (e,)).fetchall()
    print(f"  {e:<38} стоп-лист: {[dict(x) for x in s] or '—'} | "
          f"проба: {[dict(x) for x in p] or '—'}")

print("\n== баунсы по дням ==")
for d, n in c.execute(
        "SELECT substr(created_at,1,10) d, COUNT(*) n FROM events "
        "WHERE event_type='bounce' GROUP BY d ORDER BY d DESC LIMIT 10"):
    print(f"  {d}  {n}")
