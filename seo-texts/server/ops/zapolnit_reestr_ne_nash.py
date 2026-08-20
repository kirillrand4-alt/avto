# -*- coding: utf-8 -*-
"""Занести в реестр «не наш адресат» сегодняшние решения человека.

Берём только те причины снятия, которые говорят о САМОЙ КОМПАНИИ и не
зависят от модели. «Ждём паспорт», «писали недавно», «перепись не вышла»
— не сюда: это про данные и про время, а не про то, что писать нечего.
"""
import re
import sqlite3
import sys
from collections import Counter

sys.path.insert(0, r"C:\sender")
from sender.ne_nash import build_ne_nash                         # noqa: E402

ВЕЧНЫЕ = (
    "сайт показывает другое занятие",
    "подмена сайта",
)
КАТИТЬ = "--katit" in sys.argv
реестр = build_ne_nash()

c = sqlite3.connect(r"C:\sender\sender.db")
c.row_factory = sqlite3.Row
ряды = c.execute(
    "SELECT cr.id, COALESCE(cr.reason,'') reason, r.inn, r.company_name "
    "FROM confirm_reviews cr LEFT JOIN recipients r ON r.id=cr.recipient_id "
    "WHERE cr.status IN ('skipped','stoplist')").fetchall()

счёт = Counter()
надо = []
for r in ряды:
    п = str(r["reason"] or "")
    инн = "".join(ch for ch in str(r["inn"] or "") if ch.isdigit())
    if not инн:
        continue
    if any(м in п.lower() for м in ВЕЧНЫЕ):
        надо.append((инн, п, str(r["company_name"] or "")[:40]))
        счёт["в реестр"] += 1
    else:
        счёт["мимо (причина не вечная)"] += 1

# Убираем повторы: одна компания могла быть снята дважды.
уник = {}
for инн, п, имя in надо:
    уник.setdefault(инн, (п, имя))

print(f"карточек снятых: {len(ряды)}")
for k, n in счёт.most_common():
    print(f"  {n:>5}  {k}")
print(f"\nкомпаний в реестр: {len(уник)}")
for инн, (п, имя) in list(уник.items())[:25]:
    print(f"  {инн}  {имя:<40} {п[:80]}")

if not КАТИТЬ:
    print("\nсухой прогон. Занести — --katit")
    raise SystemExit(0)

внесено = 0
for инн, (п, имя) in уник.items():
    if реестр.записать(инн, п[:300], "разбор очереди 20.08 (человек)"):
        внесено += 1
print(f"\nвнесено в реестр: {внесено}")
print(f"всего в реестре: {len(реестр.набор())}")
