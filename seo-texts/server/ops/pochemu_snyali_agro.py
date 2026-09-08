# -*- coding: utf-8 -*-
"""Почему письма партии ушли из pending в skipped."""
import sys
from collections import Counter
sys.path.insert(0, r"C:\sender")
from sender.store import Store                                 # noqa: E402

ТЕМА = "Для качества: вопрос по сортировке зерна"
store = Store(r"C:\sender\sender.db")
счёт = Counter()
примеры = {}
with store._lock:
    for р in store._conn.execute(
            "SELECT id, status, reason, email, updated_at FROM confirm_reviews "
            " WHERE subject=? AND status<>'pending'", (ТЕМА,)):
        п = str(р["reason"] or "без причины")[:60]
        счёт[п] += 1
        примеры.setdefault(п, (р["id"], р["email"], р["updated_at"],
                                 str(р["status"])))
# ПРИГОВОР ИЛИ «УЗНАТЬ НЕЛЬЗЯ». По канону репозитория приговором считаются
# только «нет ящика» и «нет MX». «Проба не добилась ответа» - это неудача
# нашей стороны (в одном случае прямо WinError 10061, наше соединение), и
# снимать по ней письмо значит терять рабочий контакт.
классы = Counter()
спорные = []
for п, (i, поч, т, ст) in примеры.items():
    pass
for к, в in счёт.most_common():
    н = к.lower()
    if н.startswith("адрес не существует") or "нет mx" in н or "нет ящика" in н:
        классы["приговор: адреса нет"] += в
    elif н.startswith("опечатка"):
        классы["приговор: домен-опечатка"] += в
    elif "стоп-лист" in н or "suppress" in н:
        классы["стоп-лист"] += в
    elif "90" in н or "recent" in н:
        классы["писали меньше 90 дней назад"] += в
    elif н.startswith("проба не добилась ответа"):
        классы["СПОРНО: проба не смогла проверить"] += в
    else:
        классы["прочее: " + к[:40]] += в
for к, в in счёт.most_common(6):
    i, поч, т, ст = примеры[к]
    print("   %-52s %5d   пример %s %s" % (к, в, i, str(поч)[:26]))
print("")
print("=" * 74)
print("=== СНЯТЫЕ ПИСЬМА ПАРТИИ: %d ===" % sum(счёт.values()))
for к, в in классы.most_common():
    print("   %-40s %5d" % (к, в))
