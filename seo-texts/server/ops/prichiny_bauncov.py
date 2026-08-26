# -*- coding: utf-8 -*-
"""Отбивки, отказы своего почтовика и жалобы — за сегодня.

Три разные беды, и путать их нельзя:
  * ОТБИВКА — письмо ушло, но сервер получателя вернул отказ;
  * НЕ ВЫПУСТИЛ ЯЩИК — наш же почтовик не принял письмо на отправку
    (лимит, подозрение в спаме, аутентификация). Такое письмо адресату
    вообще не показывали;
  * ЖАЛОБА — получатель нажал «Спам».
"""
import json
import re
import sqlite3
import sys
from collections import Counter

ДЕНЬ = next((a for a in sys.argv[1:] if re.match(r"\d{4}-\d\d-\d\d", a)),
            "2026-08-26")
c = sqlite3.connect(r"C:\sender\sender.db", timeout=90)
c.execute("PRAGMA busy_timeout=60000")
c.row_factory = sqlite3.Row

print("=== ОТБИВКИ за %s ===" % ДЕНЬ)
ряды = c.execute(
    "SELECT e.id, e.mailbox_id, e.event_ts, e.detail_json, r.email "
    "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
    " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=? "
    " ORDER BY e.event_ts", (ДЕНЬ,)).fetchall()
print("всего: %d" % len(ряды))
поводы = Counter()
по_ящикам = Counter()
примеры = {}
for r in ряды:
    d = json.loads(r["detail_json"] or "{}")
    текст = " ".join((str(d.get("reason") or "") + " "
                      + str(d.get("snippet") or "") + " "
                      + str(d.get("status") or "") + " "
                      + str(d.get("smtp_code") or "")).split())
    н = текст.lower()
    if "no such user" in н or "нет пользователя" in н or "5.1.1" in н:
        п = "нет такого ящика"
    elif "spam" in н or "спам" in н:
        п = "принят за спам"
    elif "quota" in н or "переполн" in н or "5.2.2" in н:
        п = "ящик переполнен"
    elif "not exist" in н or "unrouteable" in н or "domain" in н:
        п = "домена или ящика нет"
    elif "greylist" in н or "4." in (str(d.get("status") or "")[:2] or ""):
        п = "серый список (временно)"
    elif "block" in н or "reject" in н or "заблок" in н:
        п = "отклонено сервером"
    else:
        п = "прочее"
    поводы[п] += 1
    по_ящикам[str(r["mailbox_id"] or "")] += 1
    примеры.setdefault(п, текст[:150])
for п, n in поводы.most_common():
    print("   %-24s %3d   %s" % (п, n, примеры.get(п, "")[:90]))
print("")
print("   по ящикам:")
for я, n in по_ящикам.most_common(8):
    print("      %-42s %d" % (str(я)[:42], n))

print("")
print("=== НЕ ВЫПУСТИЛ СВОЙ ПОЧТОВИК за %s ===" % ДЕНЬ)
ряды = c.execute(
    "SELECT status, mailbox_id, last_error, COUNT(*) n FROM messages "
    " WHERE substr(COALESCE(updated_at, created_at),1,10)=? "
    "   AND status IN ('failed','error','needs_data') "
    "   AND COALESCE(last_error,'') <> '' "
    " GROUP BY status, mailbox_id, last_error ORDER BY n DESC", (ДЕНЬ,)).fetchall()
if not ряды:
    print("   таких нет")
for r in ряды[:20]:
    print("   %-9s %-38s %3d  %s" % (r["status"], str(r["mailbox_id"])[:38],
                                     r["n"], str(r["last_error"])[:80]))

print("")
print("=== ЧТО ИМЕННО ПИШЕТ ЯНДЕКС В ОТБИВКАХ ===")
for r in c.execute(
        "SELECT e.detail_json, r.email FROM events e "
        "  LEFT JOIN recipients r ON r.id=e.recipient_id "
        " WHERE e.event_type='bounce' AND substr(e.event_ts,1,10)=? "
        " ORDER BY e.id DESC LIMIT 4", (ДЕНЬ,)):
    d = json.loads(r["detail_json"] or "{}")
    т = " ".join(str(d.get("snippet") or "").split())
    print("   --- %s" % str(r["email"])[:40])
    print("       %s" % т[:420])
    for к in ("reason", "status", "smtp_code", "failed"):
        if d.get(к):
            print("       %s: %s" % (к, str(d[к])[:120]))

print("")
print("=== ЖАЛОБЫ НА СПАМ ===")
ж = c.execute("SELECT COUNT(*) FROM events WHERE event_type='complaint'"
              ).fetchone()[0]
жд = c.execute("SELECT COUNT(*) FROM events WHERE event_type='complaint' "
               "  AND substr(event_ts,1,10)=?", (ДЕНЬ,)).fetchone()[0]
print("   всего за всё время: %d, за %s: %d" % (ж, ДЕНЬ, жд))
for r in c.execute("SELECT e.event_ts, e.mailbox_id, r.email, e.detail_json "
                   "  FROM events e LEFT JOIN recipients r ON r.id=e.recipient_id "
                   " WHERE e.event_type='complaint' ORDER BY e.event_ts DESC "
                   " LIMIT 10"):
    d = json.loads(r["detail_json"] or "{}")
    print("   %s %-34s %s" % (str(r["event_ts"])[:16], str(r["email"])[:34],
                              " ".join(str(d.get("snippet") or "").split())[:60]))

print("")
print("=== ОТПРАВЛЕНО за %s ===" % ДЕНЬ)
n = c.execute("SELECT COUNT(*) FROM messages WHERE substr(sent_at,1,10)=?",
              (ДЕНЬ,)).fetchone()[0]
print("   писем: %d" % n)
c.close()
