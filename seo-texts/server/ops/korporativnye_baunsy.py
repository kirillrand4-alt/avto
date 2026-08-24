# -*- coding: utf-8 -*-
"""Во что обошлось включение корпоративных серверов в отправку.

Свежие баунсы — не мёртвые ящики, а отказ по политике («550 5.7.1 blocked
due to security reason»). Считаем раздельно: публичные почтовики против
своих серверов, и отдельно долю политики среди отбивок.
"""
import json
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
СВОЙ = ("other", "unknown", "")

def тип(mx):
    return "свой сервер" if str(mx or "").strip().lower() in СВОЙ else "публичный"

отпр = Counter()
for р in c.execute(
        "SELECT r.mx_provider mx FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status='sent' AND substr(COALESCE(m.sent_at,m.created_at),1,10)=date('now')"):
    отпр[тип(р["mx"])] += 1

баунс = Counter()
политика = Counter()
for р in c.execute(
        "SELECT r.mx_provider mx, e.detail_json d FROM events e "
        "  JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=date('now')"):
    т = тип(р["mx"])
    баунс[т] += 1
    д = str(р["d"] or "").lower()
    if "security reason" in д or "message rejected" in д or "5.7.1" in д:
        политика[т] += 1

print("=== ЗА СУТКИ ===")
print("  %-14s %10s %8s %8s %10s" % ("", "отправлено", "баунсов", "%", "из них политика"))
for т in ("публичный", "свой сервер"):
    о, б = отпр[т], баунс[т]
    print("  %-14s %10d %8d %7.1f%% %10d"
          % (т, о, б, 100.0 * б / о if о else 0, политика[т]))
о, б = sum(отпр.values()), sum(баунс.values())
print("  %-14s %10d %8d %7.1f%% %10d"
      % ("ИТОГО", о, б, 100.0 * б / о if о else 0, sum(политика.values())))

print("\n=== ЧТО ЕЩЁ ЖДЁТ ОТПРАВКИ НА СВОИ СЕРВЕРЫ ===")
for р in c.execute(
        "SELECT m.status, COUNT(*) n FROM messages m "
        "  JOIN recipients r ON r.id=m.recipient_id "
        " WHERE m.status IN ('scheduled','queued','pending_review') "
        "   AND (r.mx_provider IS NULL OR lower(COALESCE(r.mx_provider,'')) "
        "        IN ('other','unknown','')) GROUP BY m.status"):
    print("  письма в статусе %-16s %d" % (р["status"], р["n"]))
н = c.execute(
    "SELECT COUNT(*) n FROM confirm_reviews cr JOIN recipients r ON r.id=cr.recipient_id "
    " WHERE cr.status IN ('pending','approved') AND (r.mx_provider IS NULL "
    "   OR lower(COALESCE(r.mx_provider,'')) IN ('other','unknown',''))").fetchone()["n"]
print("  карточек очереди на свои серверы: %d" % н)

print("\n=== ДОМЕНЫ, ОТКАЗАВШИЕ ПО ПОЛИТИКЕ (за сутки) ===")
for р in c.execute(
        "SELECT r.email, e.detail_json d FROM events e "
        "  JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=date('now')"):
    д = str(р["d"] or "").lower()
    if "security reason" in д or "message rejected" in д:
        print("  %s" % str(р["email"]).split("@")[-1])

print("\n=== СУППРЕСНУЛИ ЛИ МЫ ЭТИ АДРЕСА (политика ≠ мёртв) ===")
кол = [к[1] for к in c.execute("PRAGMA table_info(suppression)")]
поле = "value" if "value" in кол else "email"
н = 0
for р in c.execute(
        "SELECT r.email, e.detail_json d FROM events e "
        "  JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=date('now')"):
    д = str(р["d"] or "").lower()
    if "security reason" not in д and "message rejected" not in д:
        continue
    есть = c.execute("SELECT reason FROM suppression WHERE lower(%s)=?" % поле,
                     (str(р["email"]).lower(),)).fetchone()
    н += 1
    print("  %-34s %s" % (str(р["email"])[:34],
                          ("В СТОП-ЛИСТЕ: " + есть["reason"]) if есть else "не в стоп-листе — верно"))
if not н:
    print("  таких не было")
