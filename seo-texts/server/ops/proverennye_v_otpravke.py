# -*- coding: utf-8 -*-
"""Проверены ли пробой адреса тех писем, что стоят в отправке."""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db", timeout=20)
c.row_factory = sqlite3.Row

свод = Counter()
мёртвые = []
for р in c.execute(
        "SELECT m.id, r.email, p.verdict, p.source, p.ts "
        "  FROM messages m JOIN recipients r ON r.id=m.recipient_id "
        "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
        " WHERE m.status='scheduled'"):
    в = р["verdict"] or "ВЕРДИКТА НЕТ"
    свод[в] += 1
    if в in ("нет ящика", "нет MX"):
        мёртвые.append((р["id"], р["email"], в, р["source"]))

всего = sum(свод.values())
print("=== ПИСЬМА В ОТПРАВКЕ (scheduled): %d ===" % всего)
for к, н in свод.most_common():
    метка = ""
    if к in ("нет ящика", "нет MX"):
        метка = "  ← МЁРТВЫЙ АДРЕС, уйдёт в баунс"
    elif к == "ВЕРДИКТА НЕТ":
        метка = "  ← не проверен"
    elif к == "неясно":
        метка = "  ← проба не добилась ответа"
    print("  %-18s %5d  (%4.1f%%)%s"
          % (к, н, 100.0 * н / всего if всего else 0, метка))

if мёртвые:
    print("\n=== МЁРТВЫЕ В ОЧЕРЕДИ ОТПРАВКИ ===")
    for mid, адрес, в, ист in мёртвые[:12]:
        print("  письмо #%-6s %-34s %s [%s]" % (mid, адрес[:34], в, ист or "-"))
    print("  ---- всего: %d" % len(мёртвые))

print("\n=== А ЧТО В suppression (последний рубеж) ===")
кол = [к[1] for к in c.execute("PRAGMA table_info(suppression)")]
поле = "value" if "value" in кол else "email"
н = 0
for mid, адрес, в, ист in мёртвые:
    есть = c.execute("SELECT 1 FROM suppression WHERE lower(%s)=?" % поле,
                     (адрес.lower(),)).fetchone()
    if есть:
        н += 1
print("  из %d мёртвых в стоп-листе: %d (их отправка не выпустит)"
      % (len(мёртвые), н))
print("  БЕЗ защиты стоп-листа: %d" % (len(мёртвые) - н))

print("\n=== ТО ЖЕ ПО ВСЕЙ ОЧЕРЕДИ ПОДТВЕРЖДЕНИЯ (approved) ===")
свод2 = Counter()
for р in c.execute(
        "SELECT p.verdict FROM confirm_reviews cr "
        "  JOIN recipients r ON r.id=cr.recipient_id "
        "  LEFT JOIN addr_probe p ON lower(p.email)=lower(r.email) "
        " WHERE cr.status='approved'"):
    свод2[р["verdict"] or "ВЕРДИКТА НЕТ"] += 1
в2 = sum(свод2.values())
for к, н in свод2.most_common():
    print("  %-18s %5d  (%4.1f%%)" % (к, н, 100.0 * н / в2 if в2 else 0))
