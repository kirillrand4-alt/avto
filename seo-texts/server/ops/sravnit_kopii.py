# -*- coding: utf-8 -*-
"""Показать копии целиком и сравнить их между собой и с уже ушедшим письмом."""
import difflib
import sqlite3
import sys

ИДЫ = [int(a) for a in sys.argv[1:] if a.isdigit()]
c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
тексты = {}
for rid in ИДЫ:
    r = c.execute(
        "SELECT cr.id, cr.email, cr.subject, cr.body, r.inn, r.company_name, "
        "       r.contact_name FROM confirm_reviews cr "
        "LEFT JOIN recipients r ON r.id=cr.recipient_id WHERE cr.id=?",
        (rid,)).fetchone()
    if not r:
        print(f"#{rid} нет")
        continue
    тексты[rid] = str(r["body"] or "")
    print("=" * 74)
    print(f"#{rid} {r['company_name']} | контакт: {r['contact_name'] or '(нет)'} "
          f"| кому: {r['email']}")
    print(f"ТЕМА: {r['subject']}")
    print(тексты[rid][:900])
    # Что уже ушло этой компании.
    инн = "".join(ch for ch in str(r["inn"] or "") if ch.isdigit())
    for x in c.execute("SELECT email, subject, ts FROM send_log WHERE inn=? "
                       "ORDER BY ts", (инн,)):
        print(f"  УЖЕ УХОДИЛО: {x['ts'][:16]} -> {x['email']} | {x['subject']}")

if len(тексты) == 2:
    a, b = list(тексты.values())
    сх = difflib.SequenceMatcher(None, a, b).ratio()
    print(f"\nсходство двух текстов: {сх:.0%}")
