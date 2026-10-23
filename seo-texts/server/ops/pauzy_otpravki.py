# -*- coding: utf-8 -*-
"""Реальные паузы отправки за сегодня (владелец 23.10: «посмотри, что письма
реально отправляются с рандомной задержкой, а не в одно время»): по ящикам —
интервалы между письмами (мин/медиана/макс), разброс; по всему серверу — сколько
писем ушло в одну и ту же секунду и в окно 10 с. Только чтение.
    pauzy_otpravki.py [с_какого UTC, по умолчанию сегодня]"""
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime

от = sys.argv[1] if len(sys.argv) > 1 else datetime.utcnow().strftime("%Y-%m-%d")
c = sqlite3.connect(r"C:\sender\sender.db")
ряды = c.execute("SELECT mailbox_id, sent_at FROM messages WHERE status='sent' AND sent_at>=? ORDER BY sent_at", (от,)).fetchall()
print("писем с %s: %d" % (от, len(ряды)))
по_ящ = defaultdict(list)
for mb, sa in ряды:
    по_ящ[mb].append(datetime.fromisoformat(str(sa)[:26]))
все_инт = []
print("%-40s %4s %6s %6s %6s" % ("ящик", "шт", "мин,с", "мед,с", "макс,с"))
for mb, т in sorted(по_ящ.items()):
    инт = [(б - а).total_seconds() for а, б in zip(т, т[1:])]
    все_инт += [x for x in инт if x < 1800]
    if инт:
        print("%-40s %4d %6.0f %6.0f %6.0f" % (mb[:40], len(т), min(инт), statistics.median(инт), max(инт)))
if все_инт:
    к = Counter(int(x // 15) * 15 for x in все_инт if x < 300)
    print("\nинтервалы внутри ящика (<5 мин), корзины по 15 с:", sorted(к.items()))
сек = Counter(str(sa)[:19] for _, sa in ряды)
десять = Counter(str(sa)[:18] for _, sa in ряды)
print("писем в одну секунду (макс):", max(сек.values()) if сек else 0, "| секунд с 2+ письмами:", sum(1 for v in сек.values() if v > 1))
print("писем в одно окно 10 с (макс):", max(десять.values()) if десять else 0, "| окон с 3+:", sum(1 for v in десять.values() if v >= 3))
