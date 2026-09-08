# -*- coding: utf-8 -*-
"""Сколько писем партии стоит в очереди и все ли тексты собраны верно."""
import re, sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
store = Store(r"C:\sender\sender.db")
счёт = Counter()
битые = []
with store._lock:
    for р in store._conn.execute(
            "SELECT id, status, body, email FROM confirm_reviews "
            " WHERE subject=?", (ТЕМА,)):
        счёт[str(р["status"])] += 1
        т = str(р["body"] or "")
        if "ИМЯ_ОТПРАВИТЕЛЯ" not in т:
            битые.append((р["id"], р["email"], "нет метки имени"))
        elif "{" in т or "}" in т:
            битые.append((р["id"], р["email"], "осталась фигурная скобка"))
        elif "выращивает зерновые культуры" not in т:
            битые.append((р["id"], р["email"], "нет фразы про зерновые"))
        elif re.search(r"«[^»]*«|»[^«]*»[^ ,.]", т):
            битые.append((р["id"], р["email"], "двойные кавычки"))
        elif '"' in т:
            битые.append((р["id"], р["email"], "прямые кавычки"))
for i, п, ч in битые[:25]:
    print("   %-8s %-32s %s" % (i, str(п)[:32], ч))
print("")
print("=" * 70)
print("=== ОЧЕРЕДЬ ПАРТИИ ===")
for к, в in счёт.most_common():
    print("   %-20s %6d" % (к, в))
print("всего: %d; с замечаниями в тексте: %d" % (sum(счёт.values()), len(битые)))
