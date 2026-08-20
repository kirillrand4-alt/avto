# -*- coding: utf-8 -*-
"""Проверка на живой базе: реестр читается и режет тех, кого назвали."""
import sys

sys.path.insert(0, r"C:\sender")
from sender.ne_nash import build_ne_nash                         # noqa: E402

р = build_ne_nash()
весь = р.набор()
print(f"в реестре: {len(весь)} ИНН")
print("ВОЗДУХ (5031023670) в реестре:", р.есть("5031023670"))
print("причина:", р.причина("5031023670")[:110])
случайный = "7707083893"
print(f"посторонний {случайный} в реестре:", р.есть(случайный))
# Зеркало в обогащении — его читает отбор кандидатов.
import sqlite3                                                   # noqa: E402
with sqlite3.connect(r"C:\sender\enrich.db", timeout=30) as c:
    n = c.execute("SELECT COUNT(*) FROM ne_nash_adresat").fetchone()[0]
print("в зеркале enrich.db:", n)
