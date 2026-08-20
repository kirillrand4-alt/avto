# -*- coding: utf-8 -*-
"""Чем подтверждён каждый адрес сегодняшней очереди: был ли SMTP-диалог.

Владелец прав: пустой source — это не «неизвестно откуда», а запись до
появления колонки. Отличаем настоящую SMTP-пробу (есть код и ответ
чужого сервера) от лёгкой DNS-проверки (кода нет).
"""
import sqlite3
from collections import Counter

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.email, COALESCE(p.verdict,'') v, COALESCE(p.source,'') s, "
    "       p.code, COALESCE(p.answer,'') a "
    "FROM messages m JOIN confirm_reviews cr ON cr.message_id=m.id "
    "LEFT JOIN addr_probe p ON p.email=lower(cr.email) "
    "WHERE cr.status IN ('approved','edited') "
    "AND m.status IN ('scheduled','sending')").fetchall()

счёт = Counter()
примеры = {}
for r in ряды:
    в, s = str(r["v"]), str(r["s"]) or "(до колонки source)"
    smtp = r["code"] is not None and bool(str(r["a"]).strip())
    ключ = (в, s, "SMTP-диалог был" if smtp else "SMTP-диалога НЕ было")
    счёт[ключ] += 1
    if ключ not in примеры:
        примеры[ключ] = f"code={r['code']} {str(r['a'])[:70]}"

print(f"писем в отправке: {len(ряды)}\n")
for (в, s, d), n in счёт.most_common():
    print(f"  {n:>4}  {в:<16} {s:<22} {d}")
    print(f"        пример: {примеры[(в, s, d)]}")

живые = sum(n for (в, _s, d), n in счёт.items()
            if в == "есть" and d == "SMTP-диалог был")
print(f"\nадресов с подтверждённым ящиком (250 «recipient ok»): {живые}")
